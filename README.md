# LinkedIn Learning Downloader

#### This is largely based on [Baduker's work](https://github.com/baduker/LinkedIn_Learning_Downloader) with some minor changes and additions.


Asynchronous scraping tool to fetch LinkedIn's Learning Course Library. The script fetches an entire course along with its (if any) exercise files.

**Dependencies:**
- Python 3.6
- aiohttp
- lxml

#### Info

This script was written for educational usage only and should be used **ONLY** for personal purposes. **DO NOT SHARE THE VIDEOS.**

And make sure your LinkedIn account is **NOT** protected with 2FA.

#### Usage

Create a virtual environment with Python 3.

> pip install -r requirements.txt

In the `config.py` file, write your login info and fill the COURSES array with the slug of the the courses you want to download, for example:

`https://www.linkedin.com/learning/it-security-foundations-core-concepts/ -> it-security-foundations-core-concepts`
```
USERNAME = 'user@email.com'
PASSWORD = 'password'
COOKIE = '"li_at" cookie after login' #empty if not use cookie

COURSES = [
    'it-security-foundations-core-concepts',
    'javascript-for-web-designers-2'
]
```
Finally, run the script with:

> python3 linkedin_video_downloader.py

PS. Use responsibly.
