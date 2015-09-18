import re
from lxml import html,etree
import os,sys
import urllib2
import urllib
import argparse

#import codecs
#codecs.register(lambda name: codecs.lookup('utf-8') if name == 'cp65001' else None)

# FIXME:
# ======
#
# - Download "vedlagte miniatyrbilder". See post 77
# - Change download to fetch local cache first, then try server
# - Handle caching if default number of posts per page changes
# - Rename attachments to ATT_FILENAME to FILENAME
#

START_URL = 'http://avforum.no/forum/showthread.php?t=126778'

USE_TMP=True

POST_PER_PAGE=50

# Images that are used from e.g. CSS and needs to be pulled manually
EXTRA_IMAGES = (
    'images/misc/quote-left.png',
)

def progress(n,max,e=''):

    l=80
    p = n*80/max
    s1 = '=' * p
    s2 = ' ' * (l-p)
    print >>sys.stderr, "    [%s%s]  #%s/%s%s\r" %(s1,s2,n,max,e),

def clearprogress():
    print >>sys.stderr, ' '*120+'\r',

def log(a,verbose=0,debug=0,clear=True):
    #print DEBUG,debug,VERBOSE,verbose
    if type(a) is unicode:
        a = a.encode(errors='ignore')
    if debug:
        if DEBUG >= debug:
            if clear:
                clearprogress()
            print '>>>',a
    elif VERBOSE >= verbose:
        if clear:
            clearprogress()
        print a

def error(a):
    log('    *** ' + a)


def lprint(e):
    print etree.tostring(e,pretty_print=True)


def findclass(e,t,cls):
    d = e.xpath('%s[contains(concat(" ", normalize-space(@class), " "), " %s ")]' %(t,cls))
    return d


def cleantitle(tree):
    text = ''
    #print etree.tostring(tree)
    for e in tree.iter():
        t = e.text
        if t:
            t = t.strip()
        if t:
            text += t
    return text


def filename_pagecache(page):
    return os.path.join(TMPDIR, 'page_%04i.html' %(page))
def filename_attcache(att):
    return os.path.join(TMPDIR, str(att))
def filename_image(image):
    return os.path.join(OUTDIR, image)
def filename_attachment(filename):
    return os.path.join(OUTDIR, 'attachments',filename)
def filename_out(out):
    return os.path.join(OUTDIR, out)


def download_page(page,url=None,use_cache=True):

    fname = filename_pagecache(page)

    if use_cache and os.path.exists(fname):
        log('Reading page %s from %s' %(page,fname),debug=1)
        with open(fname,'r') as f:
            data = f.read()

    else:
        if not url:
            url = base + 'showthread.php?t=' + str(threadid)
            if page:
                url += '&page=%s' %(page)

        log('Download page %s from %s' %(page,url),debug=1)

        try:
            req = urllib2.urlopen(url)
            data = req.read()

            # Save to cache
            with open(fname, 'wb') as f:
                f.write(data)#.encode('utf-8'))

        except urllib2.HTTPError as e:
            error("%s: Failed to fetch %s" %(e.code,url))
            raise

    tree = html.fromstring(data)
    return tree


def get_attachment_cache(att):

    fname = filename_attcache(att)

    if not USE_CACHE:
        return None
    if not os.path.exists(fname):
        return None

    # Read header data from cache
    with open(fname,'rb') as f:
        header = {}
        for l in f:
            s=l.split(':')
            if len(s)==2:
                header[s[0].strip()] = s[1].strip()

    # Get the actual filename
    filename = str(att)
    cd = header.get('Content-disposition','')
    m=re.search(r'filename="(.*)"', cd)
    if m:
        filename=urllib.unquote(m.group(1)).decode('utf-8')

    # Try ATT_filename first then filename
    cache = str(att) + '_' + filename
    fcache = filename_attachment(cache)
    if not os.path.exists(fcache):
        cache = filename
        fcache = filename_attachment(cache)
        if not os.path.exists(fcache):
            return None

    size = os.path.getsize(fcache)
    if size != int(header['Content-Length']):
        return None

    return cache


def download_attachment(att,url):

    # Open connection
    req = urllib2.urlopen(url)
    header = req.info()

    # Store header data
    with open(filename_attcache(att), 'wb') as f:
        f.write(str(req.info()))

    # Get the attachment info from the header
    cd = header.getheader('Content-disposition')
    m=re.search(r'filename="(.*)"', cd)
    if m:
        filename=urllib.unquote(m.group(1)).decode('utf-8')
    filename = str(att) + '_' + filename

    log('Download attachment %s: %s' %(att,filename),debug=1)

    # Read data from the web
    data = req.read()

    length = int(header.getheader('Content-Length'))
    if len(data) != length:
            raise Exception("Missing data from server/file, want %s bytes, got %s" %(length,len(data)))

    # Write cache data
    with open(filename_attachment(filename),'wb') as f:
        f.write(data)

    return filename


def parse_page(page,tree):

    posts = []

    #
    for e in tree.xpath('//ol[@id="posts"]/li'):

        data = {
            'page': page,
        }

        # POST ID
        t = e.get('id')
        if not t:
            # Postens like og takk er ogsaa li elementer, men uten id
            continue
        m = re.search(r'post_(.*)', t)
        if not m:
            raise Exception("Missing post id")
        data['id'] = int(m.group(1))

        # POST COUNTER #1, #2, ...
        t = findclass(e,'.//a','postcounter')
        if not len(t):
            raise Exception("Missing post number")
        data['num'] = t[0].text

        # TIME AND DATE
        t = findclass(e,'.//span','date')
        if not len(t):
            raise Exception("Missing date")
        data['date'] = t[0].text

        t = findclass(e,'.//span','time')
        if not len(t):
            raise Exception("Missing time")
        data['time'] = t[0].text

        # USERNAME
        t = findclass(e,'.//a','username')
        if not len(t):
            raise Exception("Missing username")
        data['user'] = t[0].find('strong').text

        # TITLE (OPTIONAL)
        t = findclass(e,'.//h2','title')
        if len(t):
            data['title'] = cleantitle(t[0])

        # MAIN POST
        t = findclass(e, './/blockquote', 'postcontent')
        if not len(t):
            raise Exception("Missing post text")
        data['main'] = t[0]

        posts.append(data)

    return posts



#-----------------------------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument('-t', '--tmpdir', help="Temp work directory", default='tmp')
ap.add_argument('-n', '--nocache', help='Disable caching', action='store_true')
ap.add_argument('-d', '--dir', help='Output directory')
ap.add_argument('-D', '--debug', help='Enable debugging', action='count', default=0)
ap.add_argument('-v', '--verbose', help='Verbose output', action='count', default=0)
ap.add_argument('--no-images', help='Do not download images', action='store_true')
ap.add_argument('--no-attachments', help='Do not download images', action='store_true')
ap.add_argument('--nofirst', help='Do no load first page (use cache)', action='store_true')
ap.add_argument('url', help="URL to download", nargs='?', default=START_URL)

opts = ap.parse_args()
OUTDIR = opts.dir
TMPDIR = opts.tmpdir
DEBUG = opts.debug
VERBOSE = opts.verbose
USE_CACHE = not opts.nocache

log('''vGrab v1.0 -- vBulletin thread grabber
Copyright (C) 2015 Svein Seldal <sveinse@seldal.com>
Licensed under GPL3.0
''')



#-----------------------------------------------------------------------------
log("\nDownloading first page...")

if OUTDIR:
    TMPDIR=os.path.join(OUTDIR,TMPDIR)

# Ensure tmp dir
if not os.path.exists(TMPDIR):
    os.makedirs(TMPDIR)

# Load first page
if opts.nofirst:
    tree = download_page(1,use_cache=USE_CACHE)
else:
    tree = download_page(0,opts.url,use_cache=False)

# BASE URL for the site
t=tree.xpath('//head/base')[0]
base=t.attrib['href']
log("    BASE: " + base)

# Title and thread ID
t=tree.xpath('//*[@id="pagetitle"]/h1/span/a')[0]
title=t.text
log("    TITLE: " + title)

m=re.search('/(\d+)-.*', t.attrib['href'])
if m:
    threadid=int(m.group(1))
log("    THREAD ID: " + str(threadid))

# How many posts
post_count = 0
t=tree.xpath('//*[@id="postpagestats_above"]')[0].text
m = re.search('av (\d+)', t)
if m:
    post_count = int(m.group(1))
log("    POSTS: " + str(post_count))

# How many pages
pages = 0
for e in findclass(tree, '//a', 'popupctrl'):
    l = e.text
    if not l:
        continue
    m = re.search('Side \d+ av (\d+)', l)
    if m:
        pages = int(m.group(1))
log("    PAGES: " + str(pages))

# How many do we have in our cache
use_cache = [ USE_CACHE and os.path.exists(filename_pagecache(page))
              for page in range(pages+1) ]

# Always redownload the last page
prev = False
for n in range(pages,0,-1):
    if prev == False and use_cache[n] == True:
        use_cache[n] = False
        break
    prev = use_cache[n]



#-----------------------------------------------------------------------------
log("\nDownloading posts...")
num = 0

post_list = []
posts = {}

current_page = 1
while current_page <= pages:

    tree = download_page(current_page,use_cache=use_cache[current_page])

    for data in parse_page(current_page,tree):

        num += 1
        progress(num, post_count, ', page %s/%s' %(current_page,pages))

        iid = data['id']
        if iid in posts:
            raise Exception("Post %s already exists" %(iid))

        post_list.append(iid)
        posts[iid] = data

    current_page += 1

log('',clear=False)



#-----------------------------------------------------------------------------
log("\nParsing links and images...")
num = 0

attachment_fetchlist = {}
image_fetchlist = {}

for post in post_list:

    num += 1
    progress(num, post_count)

    data = posts[post]
    main = data['main']

    # Find all images we want to download
    images = main.xpath('.//img')
    for img in images:
        src=img.get('src')

        log('IMG  ' + src, debug=2)

        m = re.search(r'attachmentid=(\d+)($|&)', src)
        if m:
            iid=int(m.group(1))
            attachment_fetchlist[iid]=post
        else:
            image_fetchlist[src]=post

    # Find all links
    links = main.xpath('.//a')
    for link in links:
        href = link.get('href')

        log('LINK ' + href, debug=2)

        # Search for thread post links
        m=re.search(r'/(\d+)-.*post(\d+)$', href)
        if m:
            tid = int(m.group(1))
            pid = int(m.group(2))

            # Proceed if link point to a post in our thread
            if tid == threadid and pid in posts:
                continue

        # Links that points to attachments
        m = re.search(r'attachmentid=(\d+)($|&)', href)
        if m:
            iid=int(m.group(1))
            attachment_fetchlist[iid]=post
            continue

        log('    ' + href,verbose=1)


# Manual adds
for img in EXTRA_IMAGES:
    if img not in image_fetchlist:
        image_fetchlist[img] = True

log('',clear=False)



#-----------------------------------------------------------------------------
log("\nDownloading images...")
num = 0
maxnum = len(image_fetchlist)
failed = 0

for image in image_fetchlist:

    num += 1
    progress(num, maxnum)

    imagefile = filename_image(image)

    if USE_CACHE and os.path.exists(imagefile):
        log('Skipping image %s' %(image),debug=1)

    elif not opts.no_images:

        url = base + image
        log('Download image %s' %(url),debug=1)

        try:
            req = urllib2.urlopen(url)
            data = req.read()

            # Ensure dir exists
            path = os.path.split(imagefile)
            if not os.path.exists(path[0]):
                os.makedirs(path[0])

            # Save image
            with open(imagefile,'wb') as f:
                f.write(data)

        except urllib2.HTTPError as e:
            error("%s: Failed to fetch %s" %(e.code,url))
            failed += 1

log('',clear=False)

if failed:
    log('    FAILED TO DOWNLOAD: ' + str(failed))



#-----------------------------------------------------------------------------
log("\nDownloading attachments...")

a = os.path.join(OUTDIR,'attachments')
if not os.path.exists(a):
    os.makedirs(a)

attachments = {}
filenames = {}

num = 0
maxnum = len(attachment_fetchlist)
failed = 0

for (att,post) in attachment_fetchlist.items():

    num += 1
    progress(num, maxnum)

    log('ATT ' + str(att), debug=2)

    # Is the cache valid? -- The cache will never be valid if
    # USE_CACHE is false
    filename = get_attachment_cache(att)

    if filename:

        # Cache is OK
        log('Skipping attachment %s: %s' %(att,filename),debug=1)

    elif not opts.no_attachments:

        try:

            # Download the attachment
            url = base + 'attachment.php?attachmentid=' + str(att)
            filename = download_attachment(att,url)

        except urllib2.HTTPError as e:
            pnum = posts[post]['num']
            error("%s: Failed to fetch attachment %s for post %s" %(e.code,att,pnum))
            failed += 1

    if filename:

        # Store filenames and attachment names
        filenames[filename] = att
        attachments[att] = filename

progress(num, maxnum)
log('',clear=False)

if failed:
    log('    FAILED TO DOWNLOAD: ' +str(failed))



#-----------------------------------------------------------------------------
log("\nPreparing web pages...")
num = 0

img_count = 0
img_ext = 0
img_attachments = 0
img_missing = 0
img_other = 0
img_icons = 0

a_count = 0
a_ext = 0
a_mythread = 0
a_othread = 0
a_missing = 0
a_attachments = 0
a_other = 0

# Top-level iterator for page output
html = html.Element('ol')
html.attrib['class'] = 'posts'

for post in post_list:

    num += 1
    progress(num, post_count)

    data = posts[post]

    if 'title' in data:
        data['title'] = '<h2 class="posttitle">' + data['title'] + '</h2>'
    else:
        data['title'] = ''

    # WASH links
    main = data['main']
    main.tag = 'div'

    # Find all images
    images = main.xpath('.//img')
    for img in images:
        src=img.get('src')

        m = re.search(r'attachmentid=(\d+)($|&)', src)
        if m:
            iid=int(m.group(1))
            if iid in attachments:
                src = 'attachments/' + attachments[iid]
                img_attachments += 1
            elif iid in attachment_fetchlist:
                src = 'missing-image/' + str(iid)
                img_missing += 1
            else:
                error("Bug? Image in post %s refers to attachment %s that we don't have." %(data['num'],iid))

        elif src in image_fetchlist:
            img_icons += 1

        else:
            img_other += 1

        log('IMG ' + src, debug=2)

        img.attrib['src'] = src
        if src.startswith('http://') or src.startswith('https://'):
            img_ext += 1
        img_count += 1

    # Find all links
    links = main.xpath('.//a')
    for link in links:
        href = link.get('href')

        m=re.search('/(\d+)-.*post(\d+)$', href)
        if m:
            tid = int(m.group(1))
            pid = int(m.group(2))

            if tid == threadid and pid in posts:
                href = 'mylink/' + str(pid)
                a_mythread += 1
            else:
                a_othread += 1

        else:
            m = re.search(r'attachmentid=(\d+)($|&)', href)
            if m:
                iid=int(m.group(1))
                if iid in attachments:
                    href = 'attachments/' + attachments[iid]
                    a_attachments += 1
                elif iid in attachment_fetchlist:
                    href = 'missing-image/' + str(iid)
                    a_missing += 1
                else:
                    error("Bug? Link in post %s refers to attachment %s that we don't have." %(data['num'],iid))
            else:
                a_other += 1

        log('LINK' + src, debug=2)

        link.attrib['href'] = href
        if href.startswith('http://') or href.startswith('https://'):
            a_ext += 1
        a_count += 1

    data['main'] = etree.tostring(main,encoding='utf-8').replace('&#13;','').decode('utf-8')

    data['html'] = u'''
<li class="post">
  <div class="posthead">
    <span class="postdate">{date} {time}</span>
    <span class="postid">{id} - {num}</span>
  </div>
  <div class="postdetails">
    <div class="userinfo">
      <div class="user">{user}</div>
    </div>
    <div class="postbody">
      {title}
      {main}
    </div>
  </div>
</li>
    '''.format(**data)

print
print '    IMAGES: %s, where %s attachments, %s icons, %s missing, %s external, %s other' % (
                img_count,img_attachments,img_icons,img_missing,img_ext,img_other)
print '    LINKS : %s, where %s to this thread, %s to other threads, %s attachments, %s missing images, %s external, %s other' % (
                a_count,a_mythread,a_othread,a_attachments,a_missing,a_ext,a_other)


print "\nWriting web data..."
num = 0

outname = filename_out('top.html')
with open(outname,'w') as f:
    f.write(u'''<html lang="no">
<head>
  <meta charset="utf-8">

  <link href="vgrab.css" rel="stylesheet" />

  <title>{title}</title>
</head>

<body>
  <h1>{title}</h1>
    <ol class="posts">

'''.format(title=title).encode('utf-8'))
    for post in post_list:
        num += 1
        progress(num, post_count)
        f.write(posts[post]['html'].encode('utf-8'))
    f.write(u'''

    </ol>

</body>
</html>
'''.encode('utf-8'))
