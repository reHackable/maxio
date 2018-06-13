#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys

from contextlib import contextmanager
from pathlib import Path
from tempfile import mkdtemp

import PyPDF2
import paramiko

from rM2svg import lines2svg

__prog_name__ = "exportNotebook"
__version__ = "0.0.1beta"

REMARKABLE_IP = "10.11.99.1"
REMARKABLE_H, REMARKABLE_W = 1872, 1404
TPL_PATH = "/usr/share/remarkable/templates/"
XOCHITL_PATH = ".local/share/remarkable/xochitl/"

# Requires:
# - PyPDF2, paramiko python libraries
# - rM2svg python module
# - convert (imagemagick)
# - rsvg-convert (optional, to avoid rasterizing of lines)

# NOTE: they will be None if the command is not present!
CONVERT = shutil.which("convert")
RSVG_CONVERT = shutil.which("rsvg-convert") or CONVERT


def parse_args_or_exit(argv=None):
    """
    Parse command line options
    """
    parser = argparse.ArgumentParser(prog=__prog_name__)
    parser.add_argument("prefix",
                        help="partial notebook name",
                        metavar="FILETITLE")
    parser.add_argument("-p",
                        "--password",
                        help="remarkable ssh password",
                        default=None)
    parser.add_argument("-c",
                        "--coloured",
                        help="Colour annotations for document markup.",
                        action='store_true')
    parser.add_argument("--pdftk",
                        help="Assemble the pdfs with pdftk instead of PyPDF2.",
                        action='store_true')
    parser.add_argument("-1",
                        "--singlefile",
                        help="Enable multipage svg file when calling rM2svg",
                        action='store_true',
                        )
    parser.add_argument("--keeptmp",
                        help="Do not delete temporary log files.",
                        action='store_true')
    parser.add_argument('--version',
                        action='version',
                        version='%(prog)s {version}'.format(version=__version__))
    return parser.parse_args(argv)


def get_ssh_ip():
    """
    Check if ssh configuration for "remarkable" exists.
    Return the appropriate host string for ssh.
    """
    ssh_config = Path.home().joinpath('.ssh/config')
    # pylint: disable=no-member
    if not ssh_config.is_file():
        return REMARKABLE_IP

    with open(ssh_config) as ssh:
        lines = (l.strip() for l in ssh.readlines())

    if "host remarkable" in lines:
        return "remarkable"
    else:
        return REMARKABLE_IP


@contextmanager
def get_ssh_client(password=None, keeptmp=False):
    """
    Context manager to deal with the ssh connection to the remarkable.
    """
    hostname = get_ssh_ip()
    username = "root"
    if password is None:
        password = getpass.getpass('%s password: ' % hostname)

    client = paramiko.client.SSHClient()
    client.set_missing_host_key_policy(paramiko.client.AutoAddPolicy())
    client.connect(hostname, username=username, password=password)
    yield client
    client.close()


def get_client_output(client, cmd):
    """
    Executes [cmd] with the [client] and returns a touple with the contents
    of the standard output and standard error.
    It raises OSError if the command fails.
    """
    stdin, stdout, stderr = client.exec_command(cmd)
    stdout.channel.recv_exit_status()
    out, err = stdout.readlines(), stderr.readlines()
    stdin.close()
    stdout.close()
    stderr.close()
    return out, err


def get_notebook_id(client, prefix):
    """
    Return the notebook prefix (Newest notebook matching the name)
    """
    out, err = get_client_output(
        client,
        " | ".join([
            "ls -rt {}*.metadata".format(XOCHITL_PATH),
            "xargs fgrep -l {}".format(prefix),
            "tail -n1",
            "cut -d. -f1,2"
        ]))

    if err:
        print("error: {}".format(err), file=sys.stderr)

    if err and not out:
        return None

    notebook_id = out.pop().strip()
    return notebook_id


def copy_notebook_data(client, tmp, notebook_id):
    """
    Copies the notebook data and the underlying notebook pdf in tmp (if it exists).
    Returns a tuple with:
    - the list of copied (non-template) files 
    - the list of used templates in order and with repetition
      (empty if a background pdf is present)
    """
    list_files = "ls -1 {}.{{lines,pagedata,metadata,pdf}} 2>/dev/null".format(
        notebook_id)
    out, err = get_client_output(client, list_files)
    if err:
        print("error: {}".format(err))
    if err and not out:
        raise EnvironmentError(err)

    filenames = [os.path.basename(f.strip()) for f in out if f.strip()]
    templates = []

    sftp = client.open_sftp()
    try:
        for filename in filenames:
            remotepath = os.path.join(os.path.dirname(notebook_id), filename)
            localpath = os.path.join(tmp, filename)
            print("Copying {} into {}".format(remotepath, localpath))
            sftp.get(remotepath, localpath)

        if filename.endswith(".pagedata") and \
                not any(fname.endswith(".pdf") for fname in filenames):

            def get_tpl_fname(line):
                "Return template png file name from the name string"
                line = line.strip()  # do we risk to strip important whitespace?
                return "{}.png".format(line) if line else "Blank"

            with open(localpath) as pdata_f:
                templates = [
                    get_tpl_fname(line)
                    for line in pdata_f.readlines()
                ]
            for tpl_fname in set(templates):
                remotepath = os.path.join(TPL_PATH, tpl_fname)
                localpath = os.path.join(tmp, tpl_fname)
                print("Copying {} into {}".format(remotepath, localpath))
                sftp.get(remotepath, localpath)

    finally:
        sftp.close()

    filenames
    return filenames, templates


def get_extended_metadata(tmp, notebook_id, templates):
    """
    Get notebook metadata.
    Returns a dictionary with the following keys:
    [ "deleted", "lastModified", "metadatamodified", "modified", "parent"
    , "pinned", "synced", "type", "version", "visibleName"
    , "pages", "templates"
    ]
    """
    metadata_path = os.path.join(
        tmp,
        "{}.metadata".format(os.path.basename(notebook_id))
    )
    with open(metadata_path) as meta_f:
        metadata = json.load(meta_f)
    metadata["pages"] = len(templates)
    metadata["templates"] = templates
    return metadata


def get_background_original_geometry(pdfname):
    """
    Read PDF dimensions of background_original for scale correction.
    Returns the pair width, height in points (1 pt = 1/72 in)
    """
    pdf_path = os.path.join(pdfname)
    with open(pdf_path, 'rb') as pdf:
        reader = PyPDF2.PdfFileReader(pdf)
        _, _, width, height = reader.getPage(0).mediaBox
    return width, height


def prepare_background(tmp, metadata, filenames, notebook_id):
    """
    Does the magic to prepare background pdfs with the right
    templates, sizes and offsets. It requires 'convert' to be
    present in the path. Return the background pdf file path.
    """
    background = os.path.join(tmp, "background.pdf")
    # If we have copied the templates it means that we don't have a
    # base pdf. This is currently guaranteeed by the implementation of
    # copy_notebook_data
    if metadata["templates"]:
        templates_list = [
            os.path.join(tmp, template)
            for template in metadata["templates"]
        ]
        # NOTE: we are assuming here that convert exists.
        #       There is a check in main's body
        cmd = sum([
            [CONVERT],
            templates_list,
            ["-transparent", "white", background]
        ], [])
        subprocess.call(cmd)
        return background

    # If we are here we need to use the pdf to prepare the background.
    # This is currently guaranteed by the implementation of copy_notebook_data

    # If we don't have a pdf file here we need to fail
    pdf = next(fname for fname in filenames if fname.endswith(".pdf"))
    print("Found underlying document PDF, using as background.")
    bg_original = os.path.join(tmp, "background_original.pdf")
    os.symlink(
        os.path.join(tmp, pdf),
        bg_original
    )

    # use gs for now but will move to PyPDF2
    if shutil.which("gs"):
        width, height = get_background_original_geometry(bg_original)
        new_width = height / REMARKABLE_H * REMARKABLE_W
        offset = new_width - width
        print(
            "Original PDF dimensions are ({}x{}), correcting by offset of {} to fit rM foreground.".format(
                width, height, offset)
        )
        bg_offset = os.path.join(tmp, "background_with_offset.pdf")
        cmd = [
            "gs", "-q", "-sDEVICE=pdfwrite", "-dBATCH", "-dNOPAUSE",
            "-sOutputFile={}".format(bg_offset),
            "-dDEVICEWIDTHPOINTS={}".format(new_width),
            "-dDEVICEHEIGHTPOINTS={}".format(height),
            "-dFIXEDMEDIA",
            "-c", "{{{} 0 translate}}".format(offset),
            "-f", bg_original
        ]
        subprocess.call(cmd)
        os.symlink(bg_offset, background)
    else:
        print("Unable to find 'gs', skipping offset and resize of the background PDF")
        os.symlink(bg_original, background)

    return background


def prepare_foreground(tmp, filenames, singlefile, coloured):
    """
    Extract annotations and create a PDF. Returns the foreground pdf path.
    """
    output_prefix = os.path.join(tmp, "foreground")
    # If we cannot find a lines file we need to fail here
    lines_path = os.path.join(
        tmp,
        next(fname for fname in filenames if fname.endswith(".lines"))
    )
    # TODO: make the --singlefile option of rM2SVG configurable
    lines2svg(lines_path, output_prefix,
              singlefile=singlefile, coloured_annotations=coloured)

    foreground = os.path.join(tmp, "foreground.pdf")
    foreground_svgs = [str(svg) for svg in Path(tmp).glob("foreground*.svg")]
    # NOTE: here we assume that at least 'convert' is present.
    #       There is a check in main's body
    if RSVG_CONVERT is not None:
        cmd = sum([
            [RSVG_CONVERT, "-a", "-f", "pdf"],
            foreground_svgs,
            ["-o", foreground]
        ], [])
    else:
        cmd = sum([
            [CONVERT, "-density", "100"],
            foreground_svgs,
            ["-transparent", "white", foreground]
        ], [])
    subprocess.call(cmd)

    return foreground


def make_annotated_pdf(name, background, foreground, pdftk=False):
    """
    Uses the [foreground] and [background] pdfs to assemble the final
    annotated pdf called [name].pdf. It uses PyPDF2 when pdftk is False.
    """
    if not name.endswith(".pdf"):
        name = "{}.pdf".format(name)

    # NOTE: Here we assume that pdftk is present.
    #       There is a check in main's body
    if pdftk:
        # Use multistamp instead of multibackground to preserve transparency
        cmd = ["pdftk", background, "multistamp", foreground, "output", name]
        subprocess.call(cmd)
        print("Written {} to {}".format(os.stat(name).st_size, name))
    else:
        raise NotImplementedError


if __name__ == "__main__":
    args = parse_args_or_exit(sys.argv[1:])
    if CONVERT is None:
        sys.exit(
            "Unable to detect the required 'convert' executable from ImageMagick")

    tmp = mkdtemp()
    with get_ssh_client(args.password) as client:
        notebook_id = get_notebook_id(client, args.prefix)
        if not notebook_id:
            sys.exit(
                "Unable to find notebook with name containing '{}'".format(args.prefix))

        filenames, templates = copy_notebook_data(client, tmp, notebook_id)
        if not filenames:
            sys.exit("Unable to copy any file from the device")

    metadata = get_extended_metadata(tmp, notebook_id, templates)
    background = prepare_background(tmp, metadata, filenames, notebook_id)
    foreground = prepare_foreground(
        tmp, filenames, args.singlefile, args.coloured)

    if shutil.which("pdftk") is None and args.pdftk:
        sys.exit("Used --pdftk flag but the pdftk executable was not found")
    make_annotated_pdf(metadata["visibleName"],
                       background, foreground, pdftk=args.pdftk)

    if not args.keeptmp:
        print("Cleaning up temporary folder {}".format(tmp))
        shutil.rmtree(tmp)
    else:
        print("The intermediate files are available in {}".format(tmp))
