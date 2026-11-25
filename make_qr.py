"""Make a QR code for the web app link.

Usage:  python make_qr.py https://settleframe-sabit.streamlit.app
Saves settleframe_qr.png next to this file (put it on the title and demo slides).
Needs:  pip install qrcode pillow
"""
import sys
from pathlib import Path

import qrcode

url = sys.argv[1] if len(sys.argv) > 1 else "https://settleframe-sabit.streamlit.app"
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=20, border=2)
qr.add_data(url)
qr.make(fit=True)
out = Path(__file__).with_name("settleframe_qr.png")
qr.make_image(fill_color="black", back_color="white").save(out)
print(f"QR code for {url} saved to {out}")
