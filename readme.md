## Intro

[DeoVR](https://deovr.com/) is a great VR video streaming platform. It features a large amount of user-uploaded content, including many high-quality videos such as cosplay convention, various tech expos, travel vlogs, and more. The video resolution is also very high, with regular users able to watch single-eye 4160p videos for free. However, DeoVR does have a downside: videos that were previously available for free may become exclusive to members after some time. Therefore, for videos you really like, it's crucial to download them.

Currently, only members of DeoVR can download 3 videos per month. And the yt-dlp project does not yet support the DeoVR website.

To address the above issues, this script is used to download videos from DeoVR offline.

## Usage

```shell
pip install -r requirements.txt
```

```shell
python deovr_downloader.py -u https://deovr.com/oraehm
```

help:

```shell
usage: deovr_downloader.py [-h] [-u URL] [-O OUTPUT_DIR] [-t TITLE] [-c CODE] [-C CHUNCK_SIZE]

Download url from deovr

optional arguments:
  -h, --help            show this help message and exit
  -u URL, --url URL     URL of deovr web page
  -O OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Output file dir
  -t TITLE, --title TITLE
                        filename = <title>.mp4
  -c CODE, --code CODE  select codec
  -C CHUNCK_SIZE, --chunck-size CHUNCK_SIZE
                        Download in chunks of n bytes

```
