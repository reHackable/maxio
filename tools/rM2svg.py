#!/usr/bin/env python3
import sys
import struct
import os.path
import argparse


__prog_name__ = "rM2svg"
__version__ = "0.0.1beta"


# Size
DEFAULT_WIDTH = 1404
DEFAULT_HEIGHT = 1872

# Mappings
STROKE_BW = {
    0: "black",
    1: "grey",
    2: "white",
}


STROKE_C = {
    0: "blue",
    1: "red",
    2: "white",
    3: "yellow"
}

'''stroke_width={
    0x3ff00000: 2,
    0x40000000: 4,
    0x40080000: 8,
}'''


def main():
    parser = argparse.ArgumentParser(prog=__prog_name__)
    parser.add_argument("-1",
                        "--singlefile",
                        help="Enable multipage svg file",
                        action='store_true',
                        )
    parser.add_argument("-i",
                        "--input",
                        help=".lines input file",
                        required=True,
                        metavar="FILENAME",
                        #type=argparse.FileType('r')
                        )
    parser.add_argument("-o",
                        "--output",
                        help="prefix for output files",
                        required=True,
                        metavar="NAME",
                        #type=argparse.FileType('w')
                        )
    parser.add_argument("-c",
                        "--coloured_annotations",
                        help="Colour annotations for document markup.",
                        action='store_true',
                        )
    parser.add_argument('-x', '--width', default=DEFAULT_WIDTH, type=int)
    parser.add_argument('-y', '--height', default=DEFAULT_HEIGHT, type=int)
    parser.add_argument('--version',
                        action='version',
                        version='%(prog)s {version}'.format(version=__version__))
    args = parser.parse_args()

    if not os.path.exists(args.input):
        parser.error('The file "{}" does not exist!'.format(args.input))

    lines2svg(args.input, args.output, args.singlefile, args.coloured_annotations, width=args.width, height=args.height)


def abort(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def lines2svg(input_file, output_name, singlefile, coloured_annotations, width, height):
    # set the correct color map
    stroke_colour = STROKE_C if coloured_annotations else STROKE_BW

    # Read the file in memory. Consider optimising by reading chunks.
    with open(input_file, 'rb') as f:
        data = f.read()
    offset = 0

    if output_name.endswith(".svg") and not singlefile:
        output_name = output_name[:-4]

    # Is this a reMarkable .lines file?
    expected_header=b'reMarkable lines with selections and layers'
    if len(data) < len(expected_header) + 4:
        abort('File too short to be a valid file')

    fmt = '<{}sI'.format(len(expected_header))
    header, npages = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
    if header != expected_header or npages < 1:
        abort('Not a valid reMarkable file: <header={}><npages={}>'.format(header, npages))

    if singlefile:
        output = open(output_name, 'w')
        output.write('<svg xmlns="http://www.w3.org/2000/svg" height="{}" width="{}">'.format(height, width)) # BEGIN Notebook
        output.write('''
            <script type="application/ecmascript"> <![CDATA[
                var visiblePage = 'p0';
                function goToPage(page) {
                    document.getElementById(visiblePage).setAttribute('style', 'display: none');
                    document.getElementById(page).setAttribute('style', 'display: inline');
                    visiblePage = page;
                }
            ]]> </script>
        ''')

    def start_scale():
        zoom = width / DEFAULT_WIDTH
        output.write('<g transform="scale(%.03f %.03f)">' % (zoom, zoom))

    def end_scale():
        output.write('</g>')

    # Iterate through pages (There is at least one)
    for page in range(npages):
        if singlefile:
            output.write('<g id="p{}" style="display:{}">'.format(page, 'none' if page != 0 else 'inline')) # Opening page group, visible only for the first page.
            start_scale()
        else:
            output = open("{}_{:02}.svg".format(output_name, page+1), 'w')
            output.write('<svg xmlns="http://www.w3.org/2000/svg" height="{}" width="{}">\n'.format(height, width)) # BEGIN page
            start_scale()

        fmt = '<BBH' # TODO might be 'I'
        nlayers, b_unk, h_unk = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
        if b_unk != 0 or h_unk != 0: # Might indicate which layers are visible.
            print('Unexpected value on page {} after nlayers'.format(page + 1))

        # Iterate through layers on the page (There is at least one)
        for _layer in range(nlayers):
            fmt = '<I'
            (nstrokes,) = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)

            # Iterate through the strokes in the layer (If there is any)
            for _stroke in range(nstrokes):
                fmt = '<IIIfI'
                pen, colour, _i_unk, width, nsegments = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                opacity = 1
                last_x = -1.; last_y = -1.
                #if i_unk != 0: # No theory on that one
                    #print('Unexpected value at offset {}'.format(offset - 12))
                if pen == 0 or pen == 1:
                    pass # Dynamic width, will be truncated into several strokes
                elif pen == 2 or pen == 4: # Pen / Fineliner
                    width = 32 * width * width - 116 * width + 107
                elif pen == 3: # Marker
                    width = 64 * width - 112
                    opacity = 0.9
                elif pen == 5: # Highlighter
                    width = 30
                    opacity = 0.2
                    if coloured_annotations:
                        colour = 3
                elif pen == 6: # Eraser
                    width = 1280 * width * width - 4800 * width + 4510
                    colour = 2
                elif pen == 7: # Pencil-Sharp
                    width = 16 * width - 27
                    opacity = 0.9
                elif pen == 8: # Erase area
                    opacity = 0.
                else:
                    print('Unknown pen: {}'.format(pen))
                    opacity = 0.

                #print('Stroke {}: pen={}, colour={}, width={}, nsegments={}'.format(stroke, pen, colour, width, nsegments))
                output.write('<polyline style="fill:none;stroke:{};stroke-width:{:.3f};opacity:{}" points="'.format(stroke_colour[colour], width, opacity)) # BEGIN stroke

                # Iterate through the segments to form a polyline
                for segment in range(nsegments):
                    fmt = '<fffff'
                    xpos, ypos, pressure, tilt, _i_unk2 = struct.unpack_from(fmt, data, offset); offset += struct.calcsize(fmt)
                    if pen == 0:
                        if 0 == segment % 8:
                            segment_width = (5. * tilt) * (6. * width - 10) * (1 + 2. * pressure * pressure * pressure)
                            #print('    width={}'.format(segment_width))
                            output.write('" /><polyline style="fill:none;stroke:{};stroke-width:{:.3f}" points="'.format(
                                        stroke_colour[colour], segment_width)) # UPDATE stroke
                            if last_x != -1.:
                                output.write('{:.3f},{:.3f} '.format(last_x, last_y)) # Join to previous segment
                            last_x = xpos; last_y = ypos
                    elif pen == 1:
                        if 0 == segment % 8:
                            segment_width = (10. * tilt -2) * (8. * width - 14)
                            segment_opacity = (pressure - .2) * (pressure - .2)
                            #print('    width={}, opacity={}'.format(segment_width, segment_opacity))
                            output.write('" /><polyline style="fill:none;stroke:{};stroke-width:{:.3f};opacity:{:.3f}" points="'.format(
                                        stroke_colour[colour], segment_width, segment_opacity)) # UPDATE stroke
                            if last_x != -1.:
                                output.write('{:.3f},{:.3f} '.format(last_x, last_y)) # Join to previous segment
                            last_x = xpos; last_y = ypos

                    output.write('{:.3f},{:.3f} '.format(xpos, ypos)) # BEGIN and END polyline segment

                output.write('" />\n') # END stroke

        if singlefile:
            # Overlay the page with a clickable rect to flip pages
            output.write('<rect x="0" y="0" width="{}" height="{}" fill-opacity="0" onclick="goToPage(\'p{}\')" />'.format(x_width, y_width, (page + 1) % npages))
            end_scale()
            output.write('</g>') # Closing page group
        else:
            end_scale()
            output.write('</svg>') # END page
            output.close()

    if singlefile:
        output.write('</svg>') # END notebook
        output.close()

if __name__ == "__main__":
    main()
