# Printed setup guide

A one-page, letter-size setup guide to put in the box with a LayerHound board: connect it, open the dashboard, create the admin account and add printers. Two QR codes open `http://layerhound.local` and the online [owner's guide](../GUIDE.md).

| File | What it is |
|---|---|
| `LayerHound-setup-guide.pdf` | Ready to print, one side of a letter-size sheet. Print at **100% / actual size** so the QR codes stay sharp. |
| `setup-guide.html` | The guide itself. Edit the text here. |
| `build_setup_guide.py` | Fills in the QR codes and prints the page to the PDF with Chrome. It stops if the text no longer fits on one page. |

## Rebuilding the PDF

Run from the project folder (needs Google Chrome installed):

```bash
python3 -m venv .venv-print
.venv-print/bin/pip install -r docs/print/requirements.txt
.venv-print/bin/python docs/print/build_setup_guide.py
```

When the dashboard's setup steps change, update the guide here too, and the [owner's guide](../GUIDE.md).
