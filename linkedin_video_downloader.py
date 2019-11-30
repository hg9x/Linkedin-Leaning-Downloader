import os
import re
import math
import time
import logging
import json
from itertools import chain, filterfalse, starmap
from collections import namedtuple
from urllib.parse import urljoin
from config import USERNAME, PASSWORD, COURSES, PROXY, BASE_DOWNLOAD_PATH, COOKIE


import asyncio
import aiohttp
import lxml.html
import aiohttp.cookiejar


logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)-12s %(levelname)-8s %(message)s')

CUSTOM_COOKIE = {}
CUSTOM_COOKIE['li_at'] =COOKIE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36",
    "Accept": "*/*",
}
URL = ''
URL_COOKIE = "https://www.linkedin.com/learning/"
URL_LOGIN = "https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin"
FILE_TYPE_VIDEO = ".mp4"
FILE_TYPE_SUBTITLE = ".srt"
COOKIE_JAR = aiohttp.cookiejar.CookieJar()
Course = namedtuple(
    "Course", [
        "name", "slug", "description", "chapters", 
        "exercise", "exercise_url", "exercise_size"
        ])
Chapter = namedtuple("Chapter", ["name", "videos", "index"])
Video = namedtuple("Video", ["name", "slug", "index", "filename"])


def sub_format_time(ms):
    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:02}'


def clean_dir_name(dir_name):
    # Remove starting digit and dot (e.g '1. A' -> 'A')
    # Remove bad characters         (e.g 'A: B' -> 'A B')
    no_digit = re.sub(r'^\d+\.', "", dir_name)
    no_bad_chars = re.sub(r'[\\:<>"/|?*]', "", no_digit)
    return no_bad_chars.strip()


def convert_file_size(size_in_bytes):
    if size_in_bytes == 0:
        return "OB"
    size_map = ("B", "KB", "MB", "GB")
    value = int(math.floor(math.log(size_in_bytes, 1024)))
    power = math.pow(1024, value)
    size = round(size_in_bytes / power, 2)
    converted_size = f"{size}{size_map[value]}"
    return converted_size


def build_course(course_element: dict):
    chapters = [
        Chapter(name=course['title'],
                videos=[
                    Video(name=video['title'],
                          slug=video['slug'],
                          index=idx,
                          filename=f"{str(idx).zfill(2)} - {clean_dir_name(video['title'])}{FILE_TYPE_VIDEO}"
                          )
                    for idx, video in enumerate(course['videos'], start=1)
                ],
                index=idx)
        for idx, course in enumerate(course_element['chapters'], start=1)
    ]

    logging.debug(f"exerciseFiles: {course_element['exerciseFiles']}")

    course = Course(name=course_element['title'],
                    slug=course_element['slug'],
                    description=course_element['description'],
                    chapters=chapters,
                    exercise=course_element['exerciseFiles'][0]['name'] if len(course_element['exerciseFiles']) > 0 else None,
                    exercise_size=course_element['exerciseFiles'][0]['sizeInBytes'] if len(course_element['exerciseFiles']) > 0 else None,
                    exercise_url=course_element['exerciseFiles'][0]['url'] if len(course_element['exerciseFiles']) > 0 else None)
    return course


def chapter_dir(course: Course, chapter: Chapter):
    folder_name = f"{str(chapter.index).zfill(2)} - {clean_dir_name(chapter.name)}"
    chapter_path = os.path.join(BASE_DOWNLOAD_PATH, clean_dir_name(course.name), folder_name)
    return chapter_path


async def login(username, password):
    async with aiohttp.ClientSession(headers=HEADERS, cookie_jar=COOKIE_JAR) as session:
        logging.info("[*] Login step 1 - Getting CSRF token...")
        resp = None
        body = None
        
        # Check login by username/password or Cookie
        if COOKIE == '' :
            
            resp = await session.get(URL_LOGIN, proxy=PROXY, ssl=False)
            body = await resp.text()

            # Looking for CSRF Token
            html = lxml.html.fromstring(body)
            csrf = html.xpath("//input[@name='loginCsrfParam']/@value").pop()
            logging.debug(f"[*] CSRF: {csrf}")
            data = {
                "session_key": username,
                "session_password": password,
                "loginCsrfParam": csrf,
                "isJsEnabled": False
            }

            logging.info("[*] Login step 1 - Done")
            logging.info("[*] Login step 2 - Logging In...")
            await session.post(
                urljoin(URL_LOGIN, 'uas/login-submit'), proxy=PROXY,
                data=data, ssl=False)

            if not next((x.value for x in session.cookie_jar
                        if x.key.lower() == 'li_at'), False):
                raise RuntimeError("[!] Could not login. Please check your credentials")
        
        logging.info("[*] Login step 2 - Done")
        logging.info("[*] Login step 3 - Getting x-li-identity ...")
        resp = await session.get(URL_COOKIE, proxy=PROXY, ssl=False)
        body = await resp.text()
        # Looking for x-li-identity
        html = lxml.html.fromstring(body)

        id = html.xpath('/html/body/code[1]/text()')
        idjson=json.loads(str(id[0]))

        x_li_identity = idjson['data']['enterpriseProfileHash']
        HEADERS['x-li-identity'] = x_li_identity
        logging.debug(f"[*] x-li-identity: {x_li_identity}")

        HEADERS['Csrf-Token'] = next(x.value for x in session.cookie_jar
                                     if x.key.lower() == 'jsessionid')
        logging.debug(f"[*] Csrf-Token: {HEADERS['Csrf-Token']}")
        logging.info("[*] Login step 2 - Done")


async def fetch_courses():
    for course in COURSES:
        if os.path.exists(clean_dir_name(course)):
            logging.info(f"The {course} has been already downloaded")
            return
        else:
            return await asyncio.gather(*map(fetch_course, COURSES))


async def fetch_course(course_slug):
    url = f"https://www.linkedin.com/learning-api/detailedCourses" \
        f"??fields=videos&addParagraphsToTranscript=true&courseSlug={course_slug}&q=slugs"

    async with aiohttp.ClientSession(
        headers=HEADERS, cookie_jar=COOKIE_JAR) as session:
    
        resp = await session.get(url, proxy=PROXY, headers=HEADERS, ssl=False)
        logging.debug(await resp.text())
        data = await resp.json()
        course = build_course(data['elements'][0])
        await fetch_chapters(course)
        if course.exercise is not None:
            logging.info(f'[*] Found exercise files: {course.exercise}')
            await fetch_exercises(course)
        logging.info(f'[*] Finished fetching course "{course.name}"')


async def fetch_chapters(course: Course):
    chapters_dirs = [chapter_dir(course, chapter) for chapter in course.chapters]

    # Creating all missing directories
    missing_directories = filterfalse(os.path.exists, chapters_dirs)
    for d in missing_directories:
        os.makedirs(d)

    await asyncio.gather(*chain.from_iterable(
            fetch_chapter(course, chapter) for chapter in course.chapters))


def fetch_chapter(course: Course, chapter: Chapter):
    return (fetch_video(course, chapter, video) for video in chapter.videos)


async def fetch_video(course: Course, chapter: Chapter, video: Video):
    subtitles_filename = os.path.splitext(video.filename)[0] + FILE_TYPE_SUBTITLE
    video_file_path = os.path.join(chapter_dir(course, chapter), video.filename)
    subtitle_file_path = os.path.join(
        chapter_dir(course, chapter), subtitles_filename)
    video_exists = os.path.exists(video_file_path)
    subtitle_exists = os.path.exists(subtitle_file_path)
    if video_exists and subtitle_exists:
        return

    logging.info(f"[~] Fetching course '{course.name}'"
                 f" Chapter no. {chapter.index} Video no. {video.index}")
    async with aiohttp.ClientSession(
            headers=HEADERS, cookie_jar=COOKIE_JAR) as session:
        video_url = f'https://www.linkedin.com/learning-api/' \
                    f'detailedCourses?fields=selectedVideo&addParagraphsToTranscript=' \
                    f'false&courseSlug={course.slug}&' \
                    f'q=slugs&resolution=_720&videoSlug={video.slug}'
#        print(video_url)
        data = None
        tries = 3
        for _ in range(tries):
            try:
                resp = await session.get(video_url, proxy=PROXY, headers=HEADERS, ssl=False)
                data = await resp.json()
                print('Data: ' + await resp.text())
                resp.raise_for_status()
                break
            except aiohttp.ClientResponseError:
                pass

        video_url = data['elements'][0]['selectedVideo']['url']['progressiveUrl']
        try:
            subtitles = data['elements'][0]['selectedVideo']['transcript']['lines']
        except KeyError as e:
            subtitles = ""
        duration_in_ms = int(
            data['elements'][0]['selectedVideo']['durationInSeconds']) * 1000
        if not video_exists:
            await download_file(video_url, video_file_path)

        await write_subtitles(subtitles, subtitle_file_path, duration_in_ms)

    logging.info(
        f"[~] Fetched: Chapter no. {chapter.index} Video no. {video.index}")


async def write_subtitles(subs, output_path, video_duration):
    def subs_to_lines(idx, sub):
        starts_at = sub['transcriptStartAt']
        ends_at = subs[idx]['transcriptStartAt'] \
            if idx < len(subs) else video_duration
        caption = sub['caption']
        return f"{idx}\n" \
               f"{sub_format_time(starts_at)} --> {sub_format_time(ends_at)}\n" \
               f"{caption}\n\n"

    with open(output_path, 'wb') as f:
        for line in starmap(subs_to_lines, enumerate(subs, start=1)):
            f.write(line.encode('utf8'))


async def fetch_exercises(course: Course):
    course_folder_path = os.path.join(
        BASE_DOWNLOAD_PATH, clean_dir_name(course.name), course.exercise)
    exercise_file_exists = os.path.exists(course_folder_path)
    if exercise_file_exists:
        return
    if course.exercise != None :
        logging.info(f"[~] Fetching exercise files: '{course.exercise}' "
                    f"| Size: {convert_file_size(course.exercise_size)}")
        await download_file(course.exercise_url, course_folder_path)
        logging.info(f"[~] Done fetching exercise files for '{course.name}'")


async def download_file(url, output):
    async with aiohttp.ClientSession(
            headers=HEADERS, cookie_jar=COOKIE_JAR) as session:
        async with session.get(
                url, proxy=PROXY, headers=HEADERS, ssl=False) as request:
            try:
                with open(output, 'wb') as file:
                    while True:
                        chunk = await request.content.read(1024)
                        if not chunk:
                            break
                        file.write(chunk)
            except Exception as error:
                logging.exception(f"[!] Error while downloading: '{error}'")
                if os.path.exists(output):
                    os.remove(output)


async def process():
    try:
        #async with aiohttp.ClientSession(
        #    headers=HEADERS, cookie_jar=COOKIE_JAR, cookies=CUSTOM_COOKIE) as session:
        start = time.time()
        logging.info("[*] -------------Login------------")
        logging.info("*" * len(USERNAME))
        logging.info("*" * len(PASSWORD))
        await login(USERNAME, PASSWORD)
        logging.info("[*] -------------Done-------------")
        logging.info("[*] --------Fetching Cours--------")
        await fetch_courses()
        logging.info("[*] -------------Done-------------")
        stop = time.time()
        logging.info("[*] Time taken: {:.2f} seconds.".format(stop - start))
    except aiohttp.ClientProxyConnectionError as error:
        logging.error(f"Proxy Error: {error}")
    except aiohttp.ClientConnectionError as error:
        logging.error(f"Connection Error: {error}")

async def run():
    if COOKIE == '' :
        logging.info("***** LOG-IN WITH USER/PASS *****")
        async with aiohttp.ClientSession(
            headers=HEADERS, cookie_jar=COOKIE_JAR) as session:
            await process()
    else :
        logging.info("***** LOG-IN WITH COOKIE *****")
        async with aiohttp.ClientSession(
            headers=HEADERS, cookie_jar=COOKIE_JAR, cookies=CUSTOM_COOKIE) as session:
            await process()
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
