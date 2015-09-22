import re
from lxml import html,etree
import os,sys
import urllib2
import urllib
import argparse


# FIXME:
# ======
#
# - Download "vedlagte miniatyrbilder". See post 77
# - Handle caching if default number of posts per page changes
# - Rename attachments to ATT_FILENAME to FILENAME
# - Rewrite links that points to attachments
# - Fix download metric. "skipped"
#

# Some threads
#    Midas     126778
#    Hunsbedt   95204

AVFORUM = 'http://avforum.no/forum/showthread.php?t='

POST_PER_PAGE=50

SCREEN_WIDTH=120

# Images that are used from e.g. CSS and needs to be pulled manually
EXTRA_IMAGES = (
    'images/misc/quote-left.png',
)



#-----------------------------------------------------------------------------
def progress(n,max,e=''):

    l=(SCREEN_WIDTH-40)
    p = n*(SCREEN_WIDTH-40)/max
    s1 = '=' * p
    s2 = ' ' * (l-p)
    print >>sys.stderr, "    [%s%s]  #%s/%s%s\r" %(s1,s2,n,max,e),


def clearprogress():
    print >>sys.stderr, ' '*SCREEN_WIDTH+'\r',


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


#-----------------------------------------------------------------------------
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



#-----------------------------------------------------------------------------
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


def create_write(filename,data):
    # Ensure dir exists
    path = os.path.split(filename)
    if not os.path.exists(path[0]):
        os.makedirs(path[0])

    # Save data
    with open(filename,'wb') as f:
        f.write(data)



#-----------------------------------------------------------------------------
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
            create_write(fname,data)

        except urllib2.HTTPError as e:
            error("%s: Failed to fetch %s" %(e.code,url))
            raise

    tree = html.fromstring(data)
    return tree


RE_POST = re.compile(r'post_(.*)')

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
        m = RE_POST.search(t)
        if not m:
            raise Exception("Missing post id")
        data['post'] = int(m.group(1))

        # POST COUNTER #1, #2, ...
        t = findclass(e,'.//a','postcounter')
        if not len(t):
            raise Exception("Missing post number")
        data['num'] = t[0].text

        # TIME AND DATE
        t = findclass(e,'.//span','date')
        if not len(t):
            raise Exception("Missing date")
        data['date'] = t[0].text.replace(',','')

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
        ex = ''
        if len(t):
            data['title'] = cleantitle(t[0])
            ex = ':  ' + data['title']

        # MAIN POST
        t = findclass(e, './/blockquote', 'postcontent')
        if not len(t):
            raise Exception("Missing post text")
        data['main'] = t[0]

        log('   %-5s, %-13s %-5s, %s%s' %(data['num'],data['date'],data['time'],data['user'],ex), debug=2)

        posts.append(data)

    return posts



#-----------------------------------------------------------------------------
RE_STARTSWITH_HTTP = re.compile(r'^(https?://|mailto:)')
RE_ATTACHMENTID  = re.compile(r'attachmentid=(\d+)($|&)')
RE_ATTACHMENTID2 = re.compile(r'/attachments/.*/(\d+)')

# FIXME, Check these:
#  >>> ATT   [#1587]  att://91289
#  http://avforum.no/forum/attachments/hvilket-utstyr-har-avforums-medlemmer/91289d1335999862-aktos-hjemmekino-_mg_8958.jpg

def parse_image(url):

    log('IMG  ' + url, debug=3)

    # Any relative urls are replaced by absolute URLs
    m = RE_STARTSWITH_HTTP.match(url)
    if not m:
        if url.startswith('/'):
            error('URL %s starts with /, which is not handled correctly by this script' %(url))
        url = base + url

    # Consider only urls that belongs to this site
    if url.startswith(base):

        # Attachment references
        m = RE_ATTACHMENTID.search(url)
        if not m:
            m = RE_ATTACHMENTID2.search(url)
        if m:

            attid=int(m.group(1))
            src = 'att://' + str(attid)

            data = {
                'type'       : 'attachment',
                'attachment' : attid,
                'url'        : base + 'attachment.php?attachmentid=' + str(attid),
            }
            return (src,data)

        # Image references to within same site
        else:

            # Remove base URL prefix, and remove everything after '?'. myurl.com/ss?v=1
            filename = url.replace(base,'')
            m = filename.find('?')
            if m >= 0:
                filename = filename[:m]
            data = {
                'type'     : 'icon',
                'url'      : url,
                'filename' : filename,
            }
            return (filename,data)

    # External references
    else:

        data = {
            'type' : 'external',
            'url'  : url,
        }
        return (url,data)


#-----------------------------------------------------------------------------

# FIXME:
#   Fails on http://avforum.no/forum/member.php/28366-Johnnygrandis, post #2991 in Hunsbedt

RE_POSTID = re.compile(r'/(\d+)-(.*post(\d+))?')

def parse_link(url):

    #log('LINK  ' + url, debug=1)

    # Any relative urls are replaced by absolute URLs
    m = RE_STARTSWITH_HTTP.match(url)
    if not m:
        if url.startswith('/'):
            error('URL %s starts with /, which is not handled correctly by this script' %(url))
        url = base + url

    # Consider only urls that belongs to this site
    if url.startswith(base):

        # Search for thread post links
        m=RE_POSTID.search(url)
        if m:
            tid = int(m.group(1))
            src = 'post://' + str(tid)
            pid = None
            if m.lastindex > 1:
                pid = int(m.group(3))
                src += '/' + str(pid)

            data = {
                'type'   : 'post',
                'thread' : tid,
                'post'   : pid,
            }

            if '.php' in url and 'showthread.php' not in url:
                error('Unable to parse non-post url %s' %(url))

            else:
                return (src,data)

        # Search for acttachment links
        m = RE_ATTACHMENTID.search(url)
        if m:
            attid=int(m.group(1))
            src = 'att://' + str(attid)

            # Parse image
            (img,imgdata) = parse_image(url)

            data = {
                'type'       : 'attachment',
                'attachment' : attid,
                'image'      : img,
                'imagedata'  : imgdata,
            }
            return (src,data)

    # (Fallthrough, not just else)
    # Handle external links
    data = {
        'type' : 'external',
        'url'  : url,
    }
    return (url,data)



#-----------------------------------------------------------------------------
def download_file(img,url,filename,post=''):

    fullfilename = filename_image(filename)
    if use_cache and os.path.exists(fullfilename):
        log('Skipping download of %s' %(img),debug=1)

    else:
        try:
            log('Download image %s' %(url),debug=1)
            req = urllib2.urlopen(url)
            data = req.read()
            create_write(fullfilename,data)

        except urllib2.HTTPError as e:
            error("[%s] %s: Failed to fetch %s" %(post,e.code,url))
            return False

    return True

RE_FILENAME = re.compile(r'filename="(.*)"')

def download_attachment(img,url,att,post=''):

    download = True

    cachefile = filename_attcache(att)
    if use_cache and os.path.exists(cachefile):

        download = False

        # Read header data from cache
        with open(cachefile,'rb') as f:
            header = {}
            for l in f:
                s=l.split(':')
                if len(s)==2:
                    header[s[0].strip()] = s[1].strip()

        # Get the actual filename from the header
        filename = str(att)
        cd = header.get('Content-disposition','')
        m=RE_FILENAME.search(cd)
        if m:
            filename=urllib.unquote(m.group(1)).decode('utf-8')

        # Try ATT_filename first then filename
        cache = str(att) + '_' + filename
        fcache = filename_attachment(cache)

        if not os.path.exists(fcache):
            cache = filename
            fcache = filename_attachment(cache)
            if not os.path.exists(fcache):
                # Redownload needed
                download = True

        if not download:
            if not os.path.exists(fcache):
                download = True

        if not download:
            size = os.path.getsize(fcache)
            if size != int(header['Content-Length']):
                download = True

        filename = cache

    # Download the file
    if not download:
        log('Skipping download of attachment %s: %s' %(att,filename),debug=1)
        return filename

    if opts.onlycache:
        return False

    try:
        # Open connection
        req = urllib2.urlopen(url)
        header = req.info()

        # Store header data
        create_write(filename_attcache(att),str(req.info()))

        # Get the attachment info from the header
        filename = str(att)
        cd = header.getheader('Content-disposition')
        m=RE_FILENAME.search(cd)
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
        create_write(filename_attachment(filename),data)

    except urllib2.HTTPError as e:
        error("[%s] %s: Failed to fetch %s" %(post,e.code,url))
        return False

    return filename


def download_image(img,data):

    t = data['type']
    if t == 'icon':
        return download_file(img,data['url'],data['filename'],post=data['post'])

    if t == 'attachment':
        filename = download_attachment(img,data['url'],data['attachment'],post=data['post'])
        if not filename:
            # FIXME: Possible option here: Should we rewrite URLs for missing images?
            data['filename'] = 'missing'
            return False
        else:
            data['filename'] = 'attachments/' + filename
            return True

    return True



#-----------------------------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument('-t', '--tmpdir', help="Temp work directory", default='tmp')
ap.add_argument('-n', '--nocache', help='Disable caching', action='store_true')
ap.add_argument('-d', '--dir', help='Output directory')
ap.add_argument('-D', '--debug', help='Enable debugging', action='count', default=0)
ap.add_argument('-v', '--verbose', help='Verbose output', action='count', default=0)
ap.add_argument('--no-images', help='Do not download images', action='store_true')
ap.add_argument('--no-attachments', help='Do not download images', action='store_true')
ap.add_argument('--onlycache', help='Only use the cache', action='store_true')
ap.add_argument('-q', '--quit', help='Quit after')
ap.add_argument('url', help="URL to download")

opts = ap.parse_args()
OUTDIR = opts.dir
TMPDIR = opts.tmpdir
DEBUG = opts.debug
VERBOSE = opts.verbose
USE_CACHE = not opts.nocache
URL = opts.url

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

# If not full URL, use the predefined prefix
if not URL.startswith('http'):
    URL = AVFORUM + URL

# Load first page
if opts.onlycache:
    tree = download_page(1,use_cache=USE_CACHE)
else:
    tree = download_page(0,URL,use_cache=False)

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
if not opts.onlycache:
    prev = False
    for n in range(pages,0,-1):
        if prev == False and use_cache[n] == True:
            use_cache[n] = False
            break
        prev = use_cache[n]

if opts.quit == 'first':
    sys.exit(0)



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

        post = data['post']
        if post in posts:
            raise Exception("Post %s already exists" %(post))

        post_list.append(post)
        posts[post] = data

    current_page += 1

log('',clear=False)

if opts.quit == 'posts':
    sys.exit(0)



#-----------------------------------------------------------------------------
log("\nParsing links and images...")
num = 0

all_images = {}
all_links = {}

images = {}
links = {}

(i_num, a_num) = (0,0)

for post in post_list:

    num += 1
    progress(num, post_count)

    postdata = posts[post]
    main = postdata['main']
    pnum = postdata['num']

    # Parse all images
    for img in main.xpath('.//img'):
        i_num += 1

        url = img.get('src')
        (imgref, data) = parse_image(url)
        all_images[url] = imgref

        if imgref not in images:
            data['post'] = pnum
            images[imgref] = data

            if data['type'] in ('attachment','icon'):
                log('IMG   [%s]  %s' %(pnum,imgref), debug=2)
            else:
                log('IMG   [%s]  %s' %(pnum,imgref), verbose=1)

    # Parse through all links
    for link in main.xpath('.//a'):
        a_num += 1

        url = link.get('href')
        (linkref, data) = parse_link(url)
        all_links[url] = linkref

        if linkref not in links:
            data['post'] = pnum
            links[linkref] = data

            if data['type'] in ('post','attachment'):
                log('LINK  [%s]  %s' %(pnum,linkref), debug=2)
            else:
                log('LINK  [%s]  %s' %(pnum,linkref), verbose=1)

        if data['type'] == 'attachment':

            # Schedule the attachment for download
            if data['image'] not in images:
                data['imagedata']['post'] = pnum
                images[data['image']] = data['imagedata']

# Manual adds
for img in EXTRA_IMAGES:
    (imgref, data) = parse_image(img)
    all_images[url] = imgref
    data['post'] = '-'
    images.setdefault(imgref, data)

log('',clear=False)

log('    %s IMAGES, %s UNIQUE' %(i_num,len(all_images)))
log('    %s LINKS, %s UNIQUE' %(a_num,len(all_links)))

if opts.quit == 'parsing':
    sys.exit(0)



#-----------------------------------------------------------------------------
log("\nDownloading images...")
num = 0
maxnum = len(images)
downloaded = 0
skipped = 0
failed = 0

for (img,data) in images.items():

    num += 1
    progress(num, maxnum)

    ok = download_image(img,data)
    if not ok:
        failed += 1
        continue

    downloaded += 1

progress(num, maxnum)
log('',clear=False)

log('    DOWNLOADED %s IMAGES, SKIPPED %s' %(downloaded,skipped))

if failed:
    log('    FAILED TO DOWNLOAD %s IMAGES' %(failed,))

if opts.quit == 'download':
    sys.exit(0)



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
    for img in main.xpath('.//img'):

        url = img.get('src')
        imgref = all_images[url]
        imgdata = images[imgref]

        if 'filename' in imgdata:
            img.attrib['src'] = imgdata['filename']

    # Find all links
    for link in main.xpath('.//a'):

        url = link.get('href')
        linkref = all_links[url]
        linkdata = links[linkref]

        #m=RE_POSTID.search(href)
        #if m:
        #    tid = int(m.group(1))
        #    pid = int(m.group(2))

        #    if tid == threadid and pid in posts:
        #        href = 'mylink/' + str(pid)
        #        a_mythread += 1
        #    else:
        #        a_othread += 1

        #else:
        #    m = RE_ATTACHMENTID.search(href)
        #    if m:
        #        iid=int(m.group(1))
        #        if iid in attachments:
        #            href = 'attachments/' + attachments[iid]
        #            a_attachments += 1
        #        elif iid in attachment_fetchlist:
        #            href = 'missing-image/' + str(iid)
        #            a_missing += 1
        #        else:
        #            error("Bug? Link in post %s refers to attachment %s that we don't have." %(data['num'],iid))
        #    else:
        #        a_other += 1

        #log('LINK' + src, debug=2)

        #link.attrib['href'] = href
        #if href.startswith('http://') or href.startswith('https://'):
        #    a_ext += 1
        #a_count += 1

    data['main'] = etree.tostring(main,encoding='utf-8').replace('&#13;','').decode('utf-8')

    data['html'] = u'''
<li class="post">
  <div class="posthead">
    <span class="postdate">{date} {time}</span>
    <span class="postid">{post} - {num}</span>
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

progress(num, post_count)
log('',clear=False)

#log('    IMAGES: %s, where %s attachments, %s icons, %s missing, %s external, %s other' % (
#                img_count,img_attachments,img_icons,img_missing,img_ext,img_other))
#log('    LINKS : %s, where %s to this thread, %s to other threads, %s attachments, %s missing images, %s external, %s other' % (
#                a_count,a_mythread,a_othread,a_attachments,a_missing,a_ext,a_other))



#-----------------------------------------------------------------------------
log("\nWriting web data...")
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

progress(num, post_count)
log('',clear=False)
