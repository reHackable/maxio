# Collection of tools for the reMarkable paper tablet
The following binaries are required running these tools:

 * python3
 * pdftk
 * ssh
 * scp
 * convert or rsvg-convert
 * optional: ghostscript and pdfinfo to account for original pdf dimensions

If you are using a Debian-based Linux system, the following command should
install all requirements:

	sudo apt-get install python3 librsvg2-bin pdftk openssh-client ghostscript

## rM2svg

Convert a .lines file to an svg file

    usage: rM2svg [-h] -i FILENAME -o NAME

    optional arguments:
      -h, --help                      show this help message and exit
      -i FILENAME, --input FILENAME   .lines input file
      -o NAME, --output NAME          prefix for output file
      --version                       show program's version number and exit

## exportNotebook

Convert a Notebook to a PDF file: Searches for the most recent Notebook whose
visible name contains NAME, and exports it as PDF file. Works also for
(annotated PDF files).

    usage: exportNotebook NAME

    $ exportNotebook Jour
    Exporting notebook "Journal" (4 pages)
    Journal.pdf

### SSH configuration

The `exportNotebook` script assumes a USB connection. If you are connected via
WiFi, you can add an entry to your `~/.ssh/config`:

    host remarkable
		   # adapt IP if necessary
           Hostname 10.11.99.1
           User root
           ForwardX11 no
           ForwardAgent no
