# Satellite-Observation-USTH

Có 5 loại ảnh : 
- Ảnh chụp 
- Ảnh sóng ngắn 
- Full color AVHRR
- Full color MSU-MR : Tệ trong buổi tối vì k có ánh sáng 
- MCIR 
- MSA 

## Satellite reception scraper

The command-line tool fetches the static page once and saves the complete HTML
response as `document.html` in `OUTPUT_DIR`. By default, it then downloads the
CADU, telemetry JSON, dataset JSON, and product CBOR linked from each reception.

### Installation

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

### Run

Set `TARGET_URL` and `OUTPUT_DIR` in `config.py`, then run:

```bash
python main.py
```

Existing files are left untouched by default. Set `OVERWRITE = True` in
`config.py` to replace `document.html` and downloaded reception files.

Downloads are streamed, retried after temporary network failures, and skipped
when the destination already exists unless `OVERWRITE = True`. If interrupted,
run the command again to skip completed files and continue.
