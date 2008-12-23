#!/usr/bin/env python
import re

short_line_length = 50

class TokenMatcher(object):

    def __init__(self, name, pattern, replace=None):
        self.name = name
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.replace = replace

    def match(self, string):
        return self.pattern.match(string)


protocol_pattern = re.compile(r'^\w+://', re.IGNORECASE)

domain_pattern = r"([-\w]+\.)+\w\w+"

_URI_pattern = ("(("                                    +
                r"(https?|webcal|feed|ftp|news|nntp)://" + # protocol
                r"([-\w]+(:[-\w]+)?@)?"                  + # authentication
                r")|www\.)"                              + # or just www.
                domain_pattern                           + # domain
                r"(/[-\w$\.+!*'(),;:@%&=?/~#]*)?"          # path
                )
_URI_end_punctuation = r"(?<![\]\.}>\)\s,?!;:\"'])"  # end punctuation

URI_pattern = _URI_pattern + _URI_end_punctuation

email_pattern = r'([^()<>@,;:\"\[\]\s]+@' + domain_pattern + ')'

image_pattern = _URI_pattern + '\.(jpe?g|png|gif)' + _URI_end_punctuation

# youtube_pattern matches:
#  http://www.youtube.com/watch?v=KKTDRqQtPO8 and
#  http://www.youtube.com/v/KKTDRqQtPO8       and
#  http://youtube.com/watch?v=KKTDRqQtPO8     and
#  http://youtube.com/v/KKTDRqQtPO8
youtube_pattern = r'http://(?:www\.)?youtube.com/(?:watch\?)?v=?/?([\w\-]{11})'
youtube_matcher = re.compile(youtube_pattern, re.IGNORECASE)

token_order = (
    TokenMatcher('NEW_LINE'   , r'(\r?\n)'), #fuck you, Microsoft!
    TokenMatcher('YOUTUBE'    , '('+youtube_pattern+')'),
    TokenMatcher('IMAGE'      , '('+image_pattern  +')'),
    TokenMatcher('URL'        , '('+URI_pattern    +')'),
    TokenMatcher('EMAIL'      , email_pattern ),

    TokenMatcher('HASH'       ,  r'([\t ]*#[\t ]+)'     ),
    TokenMatcher('DASH'       ,  r'([\t ]*-[\t ]+)'     ),
    TokenMatcher('NUMBERDOT'  ,  r'([\t ]*\d+\.[\t ]+)' ),
    TokenMatcher('ITEMSTAR'   ,  r'([\t ]*\*[\t ]+)'    ),
    TokenMatcher('BULLET'     , ur'([\t ]*\u2022[\t ]+)'),

    TokenMatcher('UNDERSCORE' , r'(_)' ),
    TokenMatcher('STAR'       , r'(\*)'),

    TokenMatcher('RIGHT_ANGLE', r'(>[\t ]*(?:>[\t ]*)*)'),

    # The following are simple, context-independent replacement tokens
    TokenMatcher('EMDASH'  , r'(--)'    , replace=unichr(8212)),
    # No way to reliably distinguish Endash from Hyphen, Dash & Minus, 
    # so we don't.  See: http://www.alistapart.com/articles/emen/

    TokenMatcher('ELLIPSIS', r'(\.\.\.)', replace=unichr(8230)),
    #TokenMatcher('SMILEY' , r'(:\))'   , replace=unichr(9786)), # smiley face, not in HTML 4.01, doesn't work in IE
    )



# The "Replacers" are context sensitive replacements, therefore they
# must be applied in-line to the string as a whole before tokenizing.
# Another option would be to keep track of previous context when
# applying tokens.
class Replacer(object):

    def __init__(self, pattern, replace):
        self.pattern = re.compile(pattern)
        self.replace = replace

    def sub(self, string):
        return self.pattern.sub(self.replace, string)


replace_list = [
    Replacer(r'(``)', unichr(8220)),
    Replacer(r"('')", unichr(8221)),

    # First we look for inter-word " and ' 
    Replacer(r'(\b"\b)', unichr(34)), # double prime
    Replacer(r"(\b'\b)", unichr(8217)), # apostrophe
    # Then we look for opening or closing " and ' 
    Replacer(r'(\b"\B)', unichr(8221)), # close double quote 
    Replacer(r'(\B"\b)', unichr(8220)), # open double quote
    Replacer(r"(\b'\B)", unichr(8217)), # close single quote
    Replacer(r"(\B'\b)", unichr(8216)), # open single quote

    # Then we look for space-padded opening or closing " and ' 
    Replacer(r'(")(\s)', unichr(8221)+r'\2'), # close double quote
    Replacer(r'(\s)(")', r'\1'+unichr(8220)), # open double quote 
    Replacer(r"(')(\s)", unichr(8217)+r'\2'), # close single quote
    Replacer(r"(\s)(')", r'\1'+unichr(8216)), # open single quote

    # Then we gobble up stand-alone ones
    Replacer(r'(`)', unichr(8216)),
    #Replacer(r'(")', unichr(8221)),
    #Replacer(r"(')", unichr(8217)),
    ]



class Token(unicode):

    def __new__(cls, name, content=''):
        self = unicode.__new__(cls, content)
        self.name = name
        return self

    def __repr__(self):
        return '%s{%s}'%(self.name, self)

    def __add__(self, extra):
        return Token(self.name, unicode.__add__(self, extra))

    def escape(string):
        out = string.replace('&', '&amp;')
        out =    out.replace('<', '&lt;' )
        out =    out.replace('>', '&gt;' )
        out =    out.encode('ascii', 'xmlcharrefreplace')
        return out

    # make escape a static method so it can be easily overriden by the
    # importing module, in case you are using Node & Token objects to
    # create XML with libxml directly, or using some other method that
    # takes care of quoting for you.
    escape = staticmethod(escape)



class Line(list):

    def __init__(self):
        self.depth = 0


    def __repr__(self):
        return 'Line[' + ''.join(map(repr, self)) + '(' + str(self.depth) + ')]'


    def __len__(self):
        return sum([len(x) for x in self])



class Node(list):

    def __new__(cls, name, *contents, **kw):
        self = list.__new__(cls)
        return self


    def __init__(self, name, *contents, **kw):
        super(list, self).__init__(self)
        self.name = name.lower()
        self.extend(contents)
        self._attributes = kw.get('attributes')


    def node_children(self):
        for n in self:
            if isinstance(n, Node):
                return True
        return False


    def __repr__(self):
        if self.name in ('br',): # Also <hr>
            # <br></br> causes double-newlines, so we do this
            return u'<%s%s/>' % (self.name, self._attribute_string())
        else:
            content = u'\n'.join(map(unicode, self))
            content = content.replace(u'\n', u'\n  ')

            interpolate = {'name'   :self.name               ,
                           'attrs'  :self._attribute_string(),
                           'content':content                 ,}

            if self.node_children():
                return u'<%(name)s%(attrs)s>\n  %(content)s\n</%(name)s>' % interpolate
            else:
                return u'<%(name)s%(attrs)s>%(content)s</%(name)s>' % interpolate


            return pat % (self.name, self._attribute_string(), content, self.name)


    def _attribute_string(self):
        if self._attributes:
            return ' ' + ' '.join(map('%s="%s"'.__mod__, self._attributes.items()))
        return ''



class URLNode(Node):


    def __new__(cls, content, internal=False):
        self = Node.__new__(cls, 'a', content)
        return self

    def __init__(self, content, internal=False):
        Node.__init__(self, 'a', content)
        self._internal = internal

    def _get_internal(self):
        return self._internal

    internal = property(_get_internal)



class LinkNode(URLNode):

    def __repr__(self):
        class_attribute = ''
        if not self._internal:
            class_attribute = 'class="external"'

        displayed_url = self[0]
        if self[0].startswith('http://'):
            displayed_url = self[0][7:]

        return u'<%s href="%s" %s>%s</%s>' % (self.name, Token.escape(self[0]),
                                             class_attribute,
                                             Token.escape(displayed_url), self.name)



class EmailNode(URLNode):
    
    def __repr__(self):
        return u'<%s href="mailto:%s">%s</%s>' % (self.name, Token.escape(self[0]), Token.escape(self[0]), self.name)



class ImageNode(Node):

    def __new__(cls, content):
        self = Node.__new__(cls, 'img', content)
        return self

    def __init__(self, content):
        Node.__init__(self, 'img', content)

    def __repr__(self):
        return u'<%s src="%s" />' % (self.name, Token.escape(self[0]))



class YouTubeNode(Node):

    def __new__(cls, content):
        self = Node.__new__(cls, 'object', content)
        return self

    def __init__(self, content):
        Node.__init__(self, 'object', attributes={'width':'425', 'height':'350',})

        ytid = youtube_matcher.match(content).groups()[0]
        url = 'http://www.youtube.com/v/'+ytid

        self.append(Node(name='param',
                         attributes={'name':'movie', 'value':url,}))
        self.append(Node('param',
                         attributes={'name':'wmode', 'value':'transparent',}))
        self.append(Node('embed',
                         attributes={'type':'application/x-shockwave-flash',
                                     'wmode':'transparent','src':url,
                                     'width':'425', 'height':'350',}))



class PottyMouth(object):

    def __init__(self, url_check_domains=(), url_white_lists=(),
                 all_links=True,       # disables all URL hyperlinking
                 image=True,          # disables <img> tags for image URLs
                 youtube=True,        # disables YouTube embedding
                 email=True,          # disables mailto:email@site.com URLs
                 all_lists=True,      # disables all lists (<ol> and <ul>)
                 unordered_list=True, # disables all unordered lists (<ul>)
                 ordered_list=True,   # disables all ordered lists (<ol>)
                 numbered_list=True,  # disables '\d+\.' lists 
                 blockquote=True,     # disables '>' <blockquote>s
                 bold=True,           # disables *bold*
                 italic=True,         # disables _italics_
                 emdash=True,         # disables -- emdash
                 ellipsis=True,       # disables ... ellipsis
                 smart_quotes=True,   # disables smart quotes
                 ):

        self._url_check_domain = None
        if url_check_domains:
            self._url_check_domain = re.compile('(\w+://)?((' + ')|('.join(url_check_domains) + '))',
                                                flags=re.I)

        self._url_white_lists  = [re.compile(w) for w in url_white_lists]
        self.smart_quotes = smart_quotes

        self.token_list = []
        for t in token_order:
            n = t.name
            if n in ('URL','IMAGE','YOUTUBE','EMAIL') and not all_links:
                continue
            elif n == 'IMAGE' and not image:                           continue
            elif n == 'YOUTUBE' and not youtube:                       continue
            elif n == 'EMAIL' and not email:                           continue
            elif n in ('HASH','DASH','NUMBERDOT','ITEMSTAR','BULLET') and not all_lists:
                continue 
            elif n in ('DASH','ITEMSTAR','BULLET') and not unordered_list:
                continue
            elif n in ('HASH','NUMBERDOT') and not ordered_list:
                continue
            elif n == 'NUMBERDOT' and not numbered_list:               continue
            elif n == 'STAR' and not bold:                             continue
            elif n == 'UNDERSCORE' and not italic:                     continue
            elif n == 'RIGHT_ANGLE' and not blockquote:                continue
            elif n == 'EMDASH' and not emdash:                         continue
            elif n == 'ELLIPSIS' and not ellipsis:                     continue

            self.token_list.append(t)


    def debug(self, *s):
        return
        print ' '.join(map(str, s))


    def tokenize(self, string):
        p = 0
        found_tokens = []
        unmatched_collection = ''
        while p < len(string):
            found_token = False
            for tm in self.token_list:
                m = tm.match(string[p:])
                if m:
                    found_token = True
                    content = m.groups()[0]
                    p += len(content)

                    if tm.replace is not None: 
                        unmatched_collection += tm.replace
                        break

                    if unmatched_collection:
                        try:
                            found_tokens.append(Token('TEXT', unmatched_collection))
                        except UnicodeDecodeError:
                            found_tokens.append(Token('TEXT', unmatched_collection.decode('utf8')))
                        except:
                            raise

                    unmatched_collection = ''

                    if tm.name == 'NEW_LINE':
                        if found_tokens and found_tokens[-1].name == 'TEXT':
                            found_tokens[-1] += ' '
                        content=' '

                    found_tokens.append(Token(tm.name, content))
                    break

            if not found_token:
                # Pull one character off the string and continue looking for tokens
                unmatched_collection += string[p]
                p += 1

        if unmatched_collection:
            found_tokens.append(Token('TEXT', unmatched_collection))

        return found_tokens


    def _find_blocks(self, tokens):
        finished = []

        current_line = Line()

        stack = []

        old_depth = 0

        for t in tokens:
            self.debug(t)

            if t.name == 'NEW_LINE':
                if current_line:
                    if current_line.depth == 0 and old_depth != 0:
                        # figure out whether we're closing >> or * here and collapse the stack accordingly
                        self.debug('\tneed to collapse the stack by' + str(old_depth))
                        top = None
                        for i in range(old_depth):
                            if stack and stack[-1].name == 'p':
                                top = stack.pop()
                            if stack and stack[-1].name == 'blockquote':
                                top = stack.pop()

                        if not stack:
                            if top is not None:
                                finished.append(top)
                            stack.append(Node('p'))
                        self.debug('\tclosing out the stack')
                        old_depth = 0
                    self.debug('\tappending line to top of stack')
                    if not stack:
                        stack.append(Node('p'))
                    stack[-1].append( current_line )
                    current_line = Line()

                elif stack:
                    if stack[-1].name in ('p','li'):
                        top = stack.pop() # the p or li
                        self.debug('\tpopped off because saw a blank line')

                        while stack:
                            if stack[-1].name in ('blockquote','ul','ol','li'):
                                top = stack.pop()
                            else:
                                break
                        if not stack:
                            finished.append(top)

            elif t.name in ('HASH','NUMBERDOT','ITEMSTAR','BULLET','DASH') and not(current_line):
                if stack and stack[-1].name == 'p':
                    top = stack.pop()
                    if current_line.depth < old_depth:
                        # pop off <blockquote> and <li> or <p>so we can apppend the new <li> in the right node
                        for i in range(old_depth - current_line.depth):
                            top = stack.pop() # the <blockquote>
                            top = stack.pop() # the previous <li> or <p>
                    if not stack:
                        finished.append(top)

                if stack and stack[-1].name == 'li':
                    stack.pop() # the previous li
                elif stack and stack[-1].name in ('ul', 'ol'):
                    pass
                else:
                    if t.name in ('HASH','NUMBERDOT'):
                        newl = Node('ol')
                    elif t.name in ('ITEMSTAR','BULLET','DASH'):
                        newl = Node('ul')
                    if stack:
                        stack[-1].append(newl)
                    stack.append(newl)

                newli = Node('li')
                stack[-1].append(newli)
                stack.append(newli)

            elif t.name == 'RIGHT_ANGLE' and not(current_line):
                new_depth = t.count('>')
                old_depth = 0

                for n in stack[::-1]:
                    if n.name == 'blockquote':
                        old_depth += 1
                    elif n.name in ('p', 'li', 'ul', 'ol'):
                        pass
                    else:
                        break

                current_line.depth = new_depth
                if new_depth == old_depth:
                    # same level, do nothing
                    self.debug('\tsame level, do nothing')
                    pass
                elif new_depth > old_depth:
                    # current_line is empty, so we just make some new nodes
                    for i in range(new_depth - old_depth):
                        if not stack:
                            newp = Node('p')
                            stack.append(newp)
                        elif stack[-1].name not in ('p', 'li'):
                            newp = Node('p')
                            stack[-1].append(newp)
                            stack.append(newp)
                        newq = Node('blockquote')
                        stack[-1].append(newq)
                        stack.append(newq)

                elif new_depth < old_depth:
                    # current line is empty, so we just pop off the existing nodes
                    for i in range(old_depth - new_depth):
                        stack.pop() # the p
                        stack.pop() # the blockquote
                old_depth = new_depth

            else:
                if stack and stack[-1].name == 'blockquote':
                    newp = Node('p')
                    stack[-1].append(newp)
                    stack.append(newp)

                if t.name == 'URL':
                    self._handle_url(t, current_line)
                elif t.name == 'YOUTUBE':
                    self._handle_youtube(t, current_line)
                elif t.name == 'IMAGE':
                    self._handle_image(t, current_line)
                elif t.name == 'EMAIL':
                    self._handle_email(t, current_line)
                elif current_line and t.strip('\t\n\r'):
                    self.debug('\tadding (possibly empty space) text token to current line')
                    current_line.append(t)
                elif t.strip():
                    self.debug('\tadding non-empty text token to current line')
                    current_line.append(t)

        if current_line:
            if not stack:
                stack.append(Node('p'))
            stack[-1].append(current_line)

        while stack:
            top = stack.pop()
            if stack and top in stack[-1]:
                pass
            else:
                finished.append(top)
            
        return finished


    def _handle_email(self, email, current_line):
        current_line.append( EmailNode(email) )


    def _handle_url(self, anchor, current_line):
        self.debug('handling', anchor)

        if not protocol_pattern.match(anchor):
            anchor = Token(anchor.name, 'http://' + anchor)

        if self._url_check_domain and self._url_check_domain.findall(anchor):
            self.debug('\tchecking urls for this domain', len(self._url_white_lists))
            for w in self._url_white_lists:
                self.debug('\t\tchecking against', str(w))
                if w.match(anchor):
                    self.debug('\t\tmatches the white lists')
                    a = self._handle_link(anchor, internal=True)
                    current_line.append(a)
                    return
            self.debug('\tdidn\'t match any white lists, making text')
            current_line.append(anchor)
        else:
            a = self._handle_link(anchor)
            current_line.append(a)


    def _handle_link(self, anchor, internal=False):
        return LinkNode(anchor, internal=internal)


    def _handle_youtube(self, t, current_line):
        ytn = YouTubeNode(t)
        current_line.append(ytn)


    def _handle_image(self, t, current_line):
        i = ImageNode(t)
        current_line.append(i)


    def _create_spans(self, sub_line):
        new_sub_line = []
        current_span = None
        for t in sub_line:
            if isinstance(t, Node):
                if current_span is not None:
                    new_sub_line.append(current_span)
                    current_span = None
                new_sub_line.append(t)
            else:
                if current_span is None:
                    current_span = Node('span')
                et = Token.escape(t)
                current_span.append(et)
        if current_span is not None:
            new_sub_line.append(current_span)

        return new_sub_line


    def _parse_line(self, line):
        """Parse bold and italic and other balanced items"""
        stack = []
        finished = []
        
        last_bold_idx = -1
        last_ital_idx = -1

        leading_space_pad = False

        def _reduce_balanced(name, last_idx, stack):
            n = Node(name)
            sub_line = self._create_spans( stack[last_idx+1:] )

            for i in range(last_idx, len(stack)):
                stack.pop()

            if sub_line:
                n.extend(sub_line)
                stack.append(n)

        for i, t in enumerate(line):
            if isinstance(t, URLNode):
                # URL nodes can go inside balanced syntax
                stack.append(t)
            elif isinstance(t, Node):
                if stack:
                    # reduce stack, close out dangling * and _
                    sub_line = self._create_spans(stack)
                    finished.extend(sub_line)
                    last_bold_idx = -1
                    last_ital_idx = -1
                    stack = []
                # add node to new_line
                finished.append(t)
            elif isinstance(t, Token):
                if t.name == 'UNDERSCORE':
                    if last_ital_idx == -1:
                        last_ital_idx = len(stack)
                        stack.append(t)
                    else:
                        _reduce_balanced('i', last_ital_idx, stack)
                        if last_ital_idx <= last_bold_idx:
                            last_bold_idx = -1
                        last_ital_idx = -1
                elif t.name in ('STAR', 'ITEMSTAR'):
                    if t.name == 'ITEMSTAR':
                        # Because ITEMSTAR gobbles up following space, we have to space-pad the next (text) token
                        leading_space_pad = True
                    if last_bold_idx == -1:
                        last_bold_idx = len(stack)
                        stack.append(t)
                    else:
                        _reduce_balanced('b', last_bold_idx, stack)
                        if last_bold_idx <= last_ital_idx:
                            last_ital_idx = -1
                        last_bold_idx = -1
                else:
                    if leading_space_pad:
                        # Because ITEMSTAR gobbled up the following space, we have to space-pad this (text) token
                        t = Token(t.name, ' '+t)
                        leading_space_pad = False
                    stack.append(t)
            else:
                raise str(type(t)) + ':' + str(t)

        if stack:
            # reduce stack, close out dangling * and _
            sub_line = self._create_spans(stack)
            finished.extend(sub_line)

        return finished


    def _parse_block(self, block):
        new_block = Node(block.name)
        current_line = None

        ppll = -1 # previous previous line length
        pll  = -1 # previous line length

        for i, item in enumerate(block):
            # collapse lines together into single lines
            if isinstance(item, Node):
                if current_line is not None:
                    # all these lines should be dealt with together
                    parsed_line = self._parse_line(current_line)
                    new_block.extend(parsed_line)

                parsed_block = self._parse_block(item)
                new_block.append(parsed_block)
                current_line = None
                ppll = -1
                pll  = -1

            elif isinstance(item, Line):
                if current_line is not None:
                    if len(item) < short_line_length:
                        # Identify short lines
                        if 0 < pll < short_line_length:
                            current_line.append(Node('BR'))
                        elif (len(block) > i+1                       and   # still items on the stack
                              isinstance(block[i+1], Line)           and   # next item is a line
                              0 < len(block[i+1]) < short_line_length   ): # next line is short
                            # the next line is short and so is this one
                            current_line.append(Node('BR'))
                    elif 0 < pll < short_line_length and 0 < ppll < short_line_length:
                        # long line at the end of a sequence of short lines
                        current_line.append(Node('BR'))
                    current_line.extend(item)
                    ppll = pll
                    pll = len(item)
                else:
                    current_line = item
                    ppll = -1
                    pll = len(item)

        if current_line is not None:
            parsed_line = self._parse_line(current_line)
            new_block.extend(parsed_line)

        return new_block


    def pre_replace(self, string):
        for r in replace_list:
            string = r.sub(string)
        return string


    def parse(self, string):
        if self.smart_quotes:
            string = self.pre_replace(string)
        tokens = self.tokenize(string)
        blocks = self._find_blocks(tokens)
        parsed_blocks = Node('div')
        for b in blocks:
            nb = self._parse_block(b)
            parsed_blocks.append(nb)
        
        return parsed_blocks



if __name__ == '__main__':
    import sys
    w = PottyMouth(url_check_domains=('www.mysite.com', 'mysite.com'),
                   url_white_lists=('https?://www\.mysite\.com/allowed/url\?id=\d+',),
                   )
    while True:
        print 'input (end with Ctrl-D)>>'
        try:
            text = sys.stdin.read()
        except KeyboardInterrupt:
            break
        if text:
            blocks = w.parse(text)
            for b in blocks:
                print b
            print '=' * 70
