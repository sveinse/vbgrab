import re
from lxml import html,etree
import os,sys
import urllib2
import urllib


# FIXME:
# ======
#
# - Implement argparse
# - Download "vedlagte miniatyrbilder". See post 77
# - Change download to fetch local cache first, then try server
# - Do progress printing to stderr
#


START_URL = 'http://avforum.no/forum/showthread.php?t=126778'

USE_TMP=True
SLURP='tmp/'

POST_PER_PAGE=50


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


def progress(n,max,e=''):

    l=80
    p = n*80/max
    s1 = '=' * p
    s2 = ' ' * (l-p)
    print "    [%s%s]  #%s/%s%s\r" %(s1,s2,n,max,e),


def clear():
    print ' '*100+'\r',


def download_page(page,url=None):

    if not url:
        url = base + 'showthread.php?t=' + str(threadid)
        if page:
            url += '&page=%s' %(page)

    if not USE_TMP:
        data = urllib2.urlopen(url).read()
    else:
        with open(SLURP + 'page_%03i.html' %(page),'r') as f:
            data = f.read()

    tree = html.fromstring(data)

    if not USE_TMP:
        with open(SLURP + 'page_%03i.html' %(page), 'wb') as f:
            f.write(data)

    return tree


class FakeHeader(object):
    def __init__(self,header):
        self.h = {}
        for l in header.splitlines():
            s=l.split(':')
            if len(s)==2:
                self.h[s[0].strip()] = s[1].strip()
    def getheader(self,header):
        return self.h.get(header)


class FakeUrl(object):
    def __init__(self,header):
        self.header = FakeHeader(header)
    def info(self):
        return self.header


def download_attachment(att):

    url = base + 'attachment.php?attachmentid=' + str(att)

    if not USE_TMP:
        req = urllib2.urlopen(url)

        with open(SLURP + str(att), 'wb') as f:
            f.write(str(req.info()))

        return req

    else:

        with open(SLURP + str(att), 'rb') as f:
            header = f.read()
            req = FakeUrl(header)

        return req


def parse_page(tree):

    posts = []

    #
    for e in tree.xpath('//ol[@id="posts"]/li'):

        data = {}

        # POST ID
        t = e.get('id')
        if not t:
            # Postens like og takk er ogsaa li elementer, men uten id
            continue
        m = re.search(r'post_(.*)', t)
        if not m:
            raise Exception("Missing post id")
        post = int(m.group(1))
        data['id'] = post

        # POST COUNTER #1, #2, ...
        t = findclass(e,'.//a','postcounter')
        if not len(t):
            raise Exception("Missing post number")
        counter = t[0].text
        data['num'] = counter

        # TIME AND DATE
        t = findclass(e,'.//span','date')
        if not len(t):
            raise Exception("Missing date")
        date = t[0].text
        data['date'] = date

        t = findclass(e,'.//span','time')
        if not len(t):
            raise Exception("Missing time")
        time = t[0].text
        data['time'] = time

        # USERNAME
        t = findclass(e,'.//a','username')
        if not len(t):
            raise Exception("Missing username")
        user = t[0].find('strong').text
        data['user'] = user

        # TITLE (OPTIONAL)
        ptitle = None
        t = findclass(e,'.//h2','title')
        if len(t):
            # Wash title
            ptitle = cleantitle(t[0])
            data['title'] = ptitle

        # MAIN POST
        t = findclass(e, './/blockquote', 'postcontent')
        if not len(t):
            raise Exception("Missing post text")
        data['main'] = t[0]

        #print "********************"
        #print "NR   :",counter
        #print "POST :",post
        #print "DATE :",date
        #print "TIME :",time
        #print "USER :",user
        #if ptitle:
        #        print "TITLE:",ptitle

        posts.append(data)

    return posts


print "vGrab v1.0 -- vBulletin thread grabber\nCopyright (C) 2015 Svein Seldal <sveinse@seldal.com>\nLicensed under GPL3.0\n"


print "\nDownloading first page..."

# Ensure tmp dir
if not os.path.exists(SLURP):
    os.makedirs(SLURP)

# Hent inn forste side
tree = download_page(0,START_URL)

# base
t=tree.xpath('//head/base')[0]
base=t.attrib['href']
print "    BASE:", base

# Tittel og ID
t=tree.xpath('//*[@id="pagetitle"]/h1/span/a')[0]
title=t.text
print "    TITLE:", title

m=re.search('/(\d+)-.*', t.attrib['href'])
if m:
    threadid=int(m.group(1))
print "    THREAD ID:", threadid

# Hvor mange innlegg siden har
post_count = 0
t=tree.xpath('//*[@id="postpagestats_above"]')[0].text
m = re.search('av (\d+)', t)
if m:
    post_count = int(m.group(1))
print "    POSTS:", post_count

# Hvor mange sider er posten paa
pages = 0
for e in findclass(tree, '//a', 'popupctrl'):
    l = e.text
    if not l:
        continue
    m = re.search('Side \d+ av (\d+)', l)
    if m:
        pages = int(m.group(1))
current_page = 0
print "    PAGES:", pages



print "\nDownloading posts..."
num = 0

post_list = []
posts = {}

while current_page < pages:

    #print "===================="
    #print "FETCHING PAGE:",current_page+1

    tree = download_page(current_page+1)

    for data in parse_page(tree):

        num += 1
        progress(num, post_count, ', page %s/%s' %(current_page+1,pages))

        iid = data['id']
        if iid in posts:
            raise Exception("Post %s already exists" %(iid))

        post_list.append(iid)
        posts[iid] = data

    current_page += 1

print



print "\nParsing links and images..."
num = 0

attachment_fetchlist = {}
image_fetchlist = {}

for post in post_list:

    num += 1
    progress(num, post_count)

    data = posts[post]
    main = data['main']

    # Find all images
    images = main.xpath('.//img')
    for img in images:
        src=img.get('src')

        #clear()
        #print '   ',src

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

        #clear()
        #print '   ',href.encode('utf-8')

        m=re.search('/(\d+)-.*post(\d+)$', href)
        if m:
            tid = int(m.group(1))
            pid = int(m.group(2))

            if tid != threadid:
                raise Exception("Unknown threadid %s" %(tid))
            if pid not in posts:
                raise Exception("Unknown postid %s" %(pid))

            continue

        m = re.search(r'attachmentid=(\d+)($|&)', href)
        if m:
            iid=int(m.group(1))
            attachment_fetchlist[iid]=post

            continue

        clear()
        print '   ',href.encode('utf-8')

print

# Manual adds
image_fetchlist['images/misc/quote-left.png'] = True

print "\nDownloading icons..."
num = 0
maxnum = len(image_fetchlist)

for image in image_fetchlist:

    num += 1
    progress(num, maxnum)

    path = os.path.split(image)
    if not os.path.exists(path[0]):
        os.makedirs(path[0])

    url = base + image
    #print url
    try:
        req = urllib2.urlopen(url)
        #print req.info()
        with open(image,'wb') as f:
            f.write(req.read())

    except urllib2.HTTPError as e:
        clear()
        print "    %s: Failed to fetch" %(e.code),url


print



print "\nDownloading attachments..."

if not os.path.exists('attachments'):
    os.makedirs('attachments')

attachments = {}
filenames = {}

num = 0
maxnum = len(attachment_fetchlist)
failed = 0

for (att,post) in attachment_fetchlist.items():

    num += 1
    progress(num, maxnum)

    pnum = posts[post]['num']

    try:
        req = download_attachment(att)

        header = req.info()
        length = int(header.getheader('Content-Length'))
        #ctype = header.getheader('Content-Type')

        disp = header.getheader('Content-disposition')
        m=re.search(r'filename="(.*)"', disp)
        if not m:
            raise Exception("Missing filename")
        filename = urllib.unquote(m.group(1)).decode('utf-8')

        if filename in filenames:
            filename = str(att) + '_' + filename
        if att in attachments:
            raise Exception("Attachment %s already fetched" %(att))
        filenames[filename] = att
        attachments[att] = filename

        fname = 'attachments/' + filename

        if not os.path.exists(fname):
            if not USE_TMP:
                data = req.read()
            else:
                # Hack. Should rather retry downloading the file
                clear()
                print "    *** Missing local file "+fname
                data = ' '*length

        else:
            with open(fname,'rb') as f:
                data=f.read()

        if len(data) != length:
            raise Exception("Missing data from server/file, want %s bytes, got %s" %(length,len(data)))

        if not USE_TMP:
            with open(fname, 'wb') as f:
                f.write(data)

        #else:
        #    clear()
        #    print "    %s: Skipping" %(fname)

    except urllib2.HTTPError as e:
        clear()
        print "    *** Failed to fetch (%s) attachment %s in post %s" %(e.code,att,pnum)
        failed += 1

    except IOError as e:
        clear()
        print "    *** Missing local attachment %s in post %s" %(att,pnum)
        failed += 1

progress(num, maxnum)
print

if failed:
    print '    FAILED TO DOWNLOAD:',failed



print "\nCreating web data..."
num = 0

img_count = 0
img_ext = 0
a_count = 0
a_ext = 0

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
    #main.attrib['class'] = 'postcontent'

    # Find all images
    images = main.xpath('.//img')
    for img in images:
        src=img.get('src')

        m = re.search(r'attachmentid=(\d+)($|&)', src)
        if m:
            iid=int(m.group(1))
            if iid in attachments:
                src = 'attachments/' + attachments[iid]
            elif iid in attachment_fetchlist:
                src = 'missing-image/' + str(iid)
            else:
                src = 'dead-link/' + str(iid)

        #clear()
        #print src

        img.attrib['src'] = src
        if src.startswith('http://'):
            img_ext += 1
        img_count += 1

    # Find all links
    links = main.xpath('.//a')
    for link in links:
        href = link.get('href')

        #clear()
        #print '   ',href.encode('utf-8')

        m=re.search('/(\d+)-.*post(\d+)$', href)
        if m:
            tid = int(m.group(1))
            pid = int(m.group(2))

            if tid == threadid and pid in posts:
                href = 'mylink/' + str(pid)

        else:
            m = re.search(r'attachmentid=(\d+)($|&)', href)
            if m:
                iid=int(m.group(1))
                if iid in attachments:
                    src = 'attachments/' + attachments[iid]

        link.attrib['href'] = href
        if href.startswith('http://'):
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
print '    IMAGES: %s, where %s external' %(img_count,img_ext)
print '    LINKS : %s, where %s external' %(a_count,a_ext)


print "\nWriting web data..."
num = 0

with open('midas.html','w') as f:
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
