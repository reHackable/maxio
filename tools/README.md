# Collection of tools for the reMarkable paper tablet
The following binaries are required running these tools:

 * python3
 * pdftk
 * ssh
 * scp
 * convert or rsvg-convert
 * bc
 * optional: ghostscript and pdfinfo to account for original pdf dimensions
 * pdfjam

If you are using a Debian-based Linux system, the following command should
install all requirements:

	sudo apt-get install python3 librsvg2-bin pdftk openssh-client ghostscript pdfjam poppler-utils bc

## rM2svg

Convert a .lines file to an svg file

    usage: rM2svn [-h] -i FILENAME -o NAME

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

## exportDocument

Export an annotated PDF file.

    usage: Usage: exportDocument <input_file.lines> <ouput.pdf>

The command expects the original PDF file <foo>.pdf to be present in the same
directory as <foo>.lines. This would be the case if you had copied the entire
`xochitl` directory from your reMarkable tablet to the development machine.
A typical workflow would be:

```bash
$ scp -r root@10.11.99.1:/home/root/.local/share/remarkable/xochitl .
$ cd xochitl
```

Say `f073469b-d37c-432f-84d1-45fdaf12400b.lines` containts the annotations of
the interested file. The original filename can be found in the `visibleName`
field in `f073469b-d37c-432f-84d1-45fdaf12400b.metadata`.

$ exportDocument f073469b-d37c-432f-84d1-45fdaf12400b.lines out.pdf

### SSH configuration

The `exportNotebook` script assumes a USB connection. If you are connected via
WiFi, you can add an entry to your `~/.ssh/config`:

    host remarkable
		   # adapt IP if necessary
           Hostname 10.11.99.1
           User root
           ForwardX11 no
           ForwardAgent no
