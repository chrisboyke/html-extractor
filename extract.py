#!/usr/bin/env python3
#
# Python3 version of html-extractor
#
#
from lxml import html
from argparse import ArgumentParser

import logging
import os
import re
import requests
import sys
import urllib
import config_util, json
import filecmp


HEADER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36"
}


WEBFILES_START_TAG_SEARCHREPLACE = "===webfiles_start_tag==="
WEBFILES_END_TAG_SEARCHREPLACE = "===webfiles_end_tag==="
WEBFILES_START_TAG = "<@hst.webfile path=\""
WEBFILES_END_TAG = "\"/>"

# initiate logger
logging.basicConfig()
fh = logging.FileHandler('extract.log')
fh.setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.addHandler(fh)
config = ''


# encapsulate the path to the web resource in the webfile tag so the link works directly in Hippo
# however, lxml will escape the <@hst.webfile tag, so put placeholders that will be searched & replaced later
# has to be in a separate method, otherwise path to css files will be incorrect for extraction of css web resources
def add_webfiles_tags_to_resource_path(resource_path):
    if WEBFILES_START_TAG_SEARCHREPLACE not in resource_path:
        if not config.get('dest','type') == 'html':
            resource_path = WEBFILES_START_TAG_SEARCHREPLACE + resource_path + WEBFILES_END_TAG_SEARCHREPLACE
            logger.info(resource_path)
    return resource_path


# create folders for storing all web resources, categorized by type (CSS, fonts, etc.)
def create_folders():
    for folder in config.get('dest','folders').split(','):
        os.makedirs(os.path.join(config.get('dest','site_dir'),folder), exist_ok=True)

# download resource for URL, raise error if 404 or other error is returned
def download_resource(url,write_mode='w'):
    # download resource
    try:
        r = requests.get(url, headers=HEADER)
        r.raise_for_status()
        if write_mode=='wb':
            return r.content

        return r.text
    except requests.exceptions.HTTPError as e:
        logger.warning("HTTP Error for URL: %s, %s", url, e)
    except requests.exceptions.Timeout:
        logger.error("Error, request timed out for URL: %s", url)
    except requests.exceptions.RequestException as e:
        logger.error("-Error '%s' for URL: %s", e, url)
    except Exception as e:
        logger.error("-Error '%s' for URL: %s", e, url)


    return None


# download web resource, determine full URL and save location
# Return none if not downloaded, or no change needed.
def save_resource(url):
    include=config['source'].get('include',None)
    if include:
        found=False
        for i in include.split(','):
            if i in url:
                found = True
        if not found:
            return None

    nodownload=config['source'].get('nodownload',None)
    if nodownload:
        for n in nodownload.split(','):
            if n in url:
                return None

    origin_url=config.get('source','url')

    if WEBFILES_START_TAG_SEARCHREPLACE in url:
        return None




    logger.debug('Save resource %s',url)
    # get fully qualified URL, regardless if URL is a full URL, relative or absolute
    full_url = urllib.parse.urljoin(origin_url, url)
    logger.debug('full url %s',full_url)

    # Some image servers put crap at the end of the URL which breaks our algorithm, so just strip that out
    urlfix=config['source'].get('urlfix')
    if urlfix:
        for u in urlfix.split(','):
            if u in url:
                logger.debug('URLFIX - before ' + url)
                url = url.replace(u,'_')
                logger.debug('URLFIX - after ' + url)

    # get filename and extension of resource
    file_name = urllib.parse.urlsplit(url).path.split('/')[-1]
    if not file_name:
        logger.debug('No file name')
        return

    base,ext = filename_split(file_name)
    logger.debug('file name %s, base %s, ext %s',file_name,base,ext)


    # determine which folder the resource should be saved to (image, font, etc.)
    folder = select_folder(ext)[0]
    resource_path = "%s/%s" % (folder, file_name)
    logger.debug('Resource Path %s',resource_path)

    # add save_folder to resource path to determine path for saving the resource
    save_folder = config.get('dest','site_dir')
    save_path = "%s/%s" % (save_folder, resource_path)

    write_mode = select_folder(ext)[1]
    response = download_resource(full_url,write_mode)
    if response:
        # Process the CSS file before saving, otherwise collision detection fails.
        if ext=='css':
            print('Processing css',file_name,'at',full_url)
            response = save_resources_from_css(full_url,response,True)
        with open('tmp', write_mode) as f:
            f.write(response)
        collision = True
        count = 0
        while collision:
            if os.path.isfile(save_path):
                if not filecmp.cmp('tmp',save_path):
                    # File collision - update file name
                    logger.warning('Collision at %s',save_path)
                    count += 1
                    file_name=next_filename(file_name)
                    resource_path = "%s/%s" % (folder, file_name)
                    save_path = "%s/%s" % (save_folder, resource_path)
                else:
                    logger.debug('File already exists and is identical %s',save_path)
                    collision = False
            else:
                collision = False
        logger.debug("Saving external resource as %s with URL '%s' to '%s", write_mode, full_url, save_path)
        logger.info("Saving external resource with URL '%s' to '%s", full_url, save_path)

        os.rename('tmp',save_path)

    else:
        return None

    return resource_path

# If a filename is foo.txt, then return foo_1.txt
# if filename is foo_1.txt, then return foo_2.txt, etc.
def next_filename(filename):
    if '.' in filename:
        (base,ext) = filename.rsplit('.',1)
    else:
        base = filename
        ext = None
    m = re.search(r'(.*)_(\d+)$',base)
    if m:
        base = m.group(1) + '_' + str(int(m.group(2)) + 1)
    else:
        base = base + '_1'
    if ext:
        return base + '.' + ext
    else:
        return base

# search CSS stylesheet (string) for web resources and download them
def save_resources_from_css(css_url,stylesheet_string, external):
    # check if a style element does not contain text so no exception is raised
    if stylesheet_string:
        matches = re.finditer(r'url\((.*?)\)',stylesheet_string)
        if matches:
            for m in matches:
                url = m.group(1)
                # remove leading and trailing ' and "
                if url.startswith('\'') or url.startswith('"'):
                    sanitized_url = url[1:-1]
                else:
                    sanitized_url = url

                # check if URL is not null and does not contain binary data
                if sanitized_url and not sanitized_url.startswith('data:'):

                    # Resource paths are almost always relative to css location
                    print('Relative URL',sanitized_url)
                    css_dir = css_url.rsplit('/',1)[0] + '/'
                    print('css_dir',css_dir)
                    sanitized_url = urllib.parse.urljoin(css_dir,sanitized_url)
                    print('New url:',sanitized_url)

                    # save resource
                    resource_path = save_resource(sanitized_url)

                    if resource_path:
                        resource_path = add_webfiles_tags_to_resource_path(resource_path)
                        print("Resource path changed from",url,'to',resource_path)

                        # replace url with new path
                        stylesheet_string = stylesheet_string.replace(url,resource_path)

        if external:
            stylesheet_string = stylesheet_string.replace(WEBFILES_START_TAG_SEARCHREPLACE,'../')
            stylesheet_string = stylesheet_string.replace(WEBFILES_END_TAG_SEARCHREPLACE,'')

    return stylesheet_string


# switch-case statement used by create_folders()
# returns tuples of folder and write-mode (binary, non-binary)
def select_folder(ext):
    return {
        'css': ('css', 'w'),
        'js': ('js', 'w'),
        # images
        'gif': ('images', 'wb'),
        'jpeg': ('images', 'wb'),
        'jpg': ('images', 'wb'),
        'png': ('images', 'wb'),

        # icons
        'ico': ('icons', 'wb'),
        # fonts
        'eot': ('fonts', 'wb'),
        'svg': ('fonts', 'w'),
        'ttf': ('fonts', 'wb'),
        'woff': ('fonts', 'wb'),
        'woff2': ('fonts', 'wb'),
        'other': ('other', 'w'),
        # videos
        'mp4': ('videos', 'wb'),
        'ogv': ('videos', 'wb'),
        'webm': ('videos', 'wb'),
        'mov': ('videos', 'wb'),
    }.get(ext, ('other', 'wb'))

def filename_split(filename):
    if '.' in filename:
        return filename.rsplit('.',1)
    else:
        return filename,''

def main():
    global config
    config = config_util.read_config()

    if config.get('logging','level') == "debug":
        logging.getLogger().setLevel(logging.DEBUG)
    elif config.get('logging','level') == "info":
        logging.getLogger().setLevel(logging.INFO)

    url = config.get('source','url')

    html_filename = config['source'].get('html')
    if not html_filename:
        # download resource from URL and parse HTML
        raw_html = download_resource(config.get('source','url'))

    else:
        if os.path.isfile(html_filename):
            with open(html_filename, 'r') as f:
                raw_html = f.read()
        else:
            logger.error("Could not read HTML file: %s", html_filename)
            sys.exit(1)

    if raw_html:
        # prepare folders
        create_folders()

        # Clean up trask
        raw_html = raw_html.replace('#{{', '{{')

        # find all resources in javascript

        logger.info('FILENAMES')

        for expr in [ r'filename:"(.*?)"',
                      r'xlink:href="(.*?)"',
                      r'src=\\"(.*?)\\"',
                      r'(/assets/.*?\.js)',
                      r'data-bg-.*?="(.*?)"' ]:
            matches = re.finditer(expr,raw_html)
            if matches:
                for m in matches:
                    f = m.group(1)
                    logger.info('Found %s in %s',f,m.group(0))

                    # save resource
                    resource_path = save_resource(f)
                    if resource_path:
                        # set new path to web resource
                        resource_path = add_webfiles_tags_to_resource_path(resource_path)
                        print(resource_path)
                        raw_html = raw_html.replace(f,resource_path)

        root = html.fromstring(raw_html)

        # find all web resources in link tags that are not a stylesheet
        for elm in root.xpath("//link[@rel!='stylesheet' and @type!='text/css' and @href]"):
            if elm.get('href'):
                # save resource
                resource_path = save_resource(elm.get('href'))
                if resource_path:
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('href', resource_path)

        # find all external stylesheets
        # xpath expression returns directly the value of href
        for elm in root.xpath("//link[@rel='stylesheet' and @href or @type='text/css' and @href]"):
            if elm.get('href'):
                href = elm.get('href')
                # save resource
                resource_path = save_resource(href)
                if resource_path:

                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('href', resource_path)

        # find all web resources from elements with src attribute (<script> and <img> elements)
        # xpath expression returns directly the value of src
        for elm in root.xpath('//*[@src]'):
            if elm.get('src') and not elm.get('src').startswith('data:'):
                # save resource
                resource_path = save_resource(elm.get('src'))
                if resource_path:

                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('src', resource_path)

        # find all web resources from elements with srcset attribute (html5)
        for elm in root.xpath('//*[@srcset]'):
            images = elm.get('srcset')
            new_images = []
            for i in re.split(r'\s*,\s*',images):
                fields = re.split(r'\s+',i,1)
                img = fields[0]
                size=''
                if len(fields) == 2:
                    size = fields[1]
                # save resource
                resource_path = save_resource(img)
                if resource_path:
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    new_images.append(resource_path+' '+size)
                else:
                    # Keep as is
                    new_images.append(img+' '+size)
            elm.set('srcset', ',\n'.join(new_images))


        # find all web resources from elements with data-src attribute (HTML5)
        # xpath expression returns directly the value of data-src
        for elm in root.xpath('//*[@data-src]'):
            if elm.get('data-src'):
                # save resource
                resource_path = save_resource(elm.get('data-src'))
                if resource_path:
                    # set new path to web resource
                    resource_path = add_webfiles_tags_to_resource_path(resource_path)
                    elm.set('data-src', resource_path)

        # find web resources in inline stylesheets
        for elm in root.xpath('//style'):
            new_css = save_resources_from_css(config.get('source','url'),elm.text, False)
            if new_css:
                # set new text for element, with updated URLs
                elm.text = new_css

        # find web resources in inline styles
        # xpath expression returns directly the value of style
        for elm in root.xpath('//*[@style]'):
            new_css = save_resources_from_css(config.get('source','url'),elm.get('style'), False)
            if new_css:
                # set style with new path
                elm.set('style', new_css)

        # save ftl/html
        html_file_contents = html.tostring(root).decode('utf-8')
        file_name = os.path.join(config.get('dest','site_dir'),config.get('dest','template'))
        if not config.get('dest','type') == 'html':
            # add webfiles import tag for importing tag libraries
            html_file_contents = config.get('ftl','import_tag') + '\n'+ html_file_contents

        # replace placeholders for webfiles tags
        html_file_contents = html_file_contents.replace(WEBFILES_START_TAG_SEARCHREPLACE, WEBFILES_START_TAG)
        html_file_contents = html_file_contents.replace(WEBFILES_END_TAG_SEARCHREPLACE, WEBFILES_END_TAG)

        # save to file
        print('Writing',file_name)
        with open(file_name, 'w') as f:
            f.write(html_file_contents)
        print("Downloaded resources from {} successfully".format(url))


if __name__ == '__main__':
    main()
