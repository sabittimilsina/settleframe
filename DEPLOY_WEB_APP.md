# Put SettleFrame online (free, about 15 minutes)

The class talk needs a link the audience can open in a browser. The web version is
`streamlit_app.py`; it uses the same solver (`settleframe/`) as the desktop program.

Target link: **https://settleframe-sabit.streamlit.app**
(If that name is taken, pick another; then re-make the QR code, see step 5.)

## 1. Try it on your computer first (optional)
```
pip install streamlit pandas
streamlit run streamlit_app.py
```
A browser tab opens at http://localhost:8501. Close the terminal to stop it.

## 2. Make a GitHub repository
1. Sign in at https://github.com (create a free account if needed).
2. Click **+ → New repository**. Name: `settleframe`. Choose **Public**. Click **Create repository**.
3. On the new page click **uploading an existing file**.
4. Open the `SettleFrame` folder in File Explorer, select everything inside it
   (`streamlit_app.py`, `requirements.txt`, `packages.txt`, the `settleframe` folder,
   the `.streamlit` folder, `examples`, `staad`, `README.md`, `verify.py`, `run_app.py`, ...)
   and drag it onto the GitHub page. Do not upload `__pycache__` folders.
5. Click **Commit changes**.

Check: the repository front page must show `streamlit_app.py` and the `settleframe`
folder at the top level (not inside another folder).

## 3. Deploy on Streamlit Community Cloud
1. Go to https://share.streamlit.io and click **Continue with GitHub**. Allow access.
2. Click **Create app → Deploy a public app from GitHub**.
3. Repository: `<your-user>/settleframe` · Branch: `main` · Main file path: `streamlit_app.py`.
4. **App URL**: type `settleframe-sabit`.
5. Click **Deploy**. The first build takes 2–5 minutes; then the app opens.

## 4. Test it (the guidelines ask for this at least 24 h before the talk)
- Open the link on your phone and on a second computer.
- Change a value (e.g. Cc of F2 from 0.35 to 0.6) and press **Run analysis**; the largest
  settlement moment should go from 134 to about 160 kN·m.
- Switch Coupled / Uncoupled and move the time slider.

## 5. QR code
```
pip install qrcode pillow
python make_qr.py https://settleframe-sabit.streamlit.app
```
This writes `settleframe_qr.png`. Only needed if your link is different; the slides
already have the QR code for `settleframe-sabit.streamlit.app`.

## 6. On the day
- A free app **goes to sleep after 12 hours without visitors**. Open the link yourself
  about 30 minutes before the session. If you see "This app has gone to sleep",
  click **Yes, get this app back up!** and wait about a minute.
- Keep the backup video and screenshots in the slides in case the room Wi-Fi fails.

## Changing the app later
Edit the file on GitHub (pencil icon) or upload the new version; the app rebuilds itself
within a minute.
