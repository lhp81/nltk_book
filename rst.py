#!/usr/bin/env python
#
# Natural Language Toolkit: Documentation generation script
#
# Copyright (C) 2001-2006 University of Pennsylvania
# Author: Edward Loper <edloper@gradient.cis.upenn.edu>
# URL: <http://nltk.sf.net>
# For license information, see LICENSE.TXT

r"""
This is a customized driver for converting docutils reStructuredText
documents into HTML and LaTeX.  It customizes the standard writers in
the following ways:
    
    - Source code highlighting is added to all doctest blocks.  In
      the HTML output, highlighting is performed using css classes:
      'pysrc-prompt', 'pysrc-keyword', 'pysrc-string', 'pysrc-comment',
      and 'pysrc-output'.  In the LaTeX output, highlighting uses five
      new latex commands: '\pysrcprompt', '\pysrckeyword',
      '\pysrcstring', '\pysrccomment', and '\pyrcoutput'.

    - A new "example" directive is defined.

    - A new "doctest-ignore" directive is defined.

    - A new "tree" directive is defined.

    - New directives "def", "ifdef", and "ifndef", which can be used
      to conditionally control the inclusion of sections.  This is
      used, e.g., to make sure that the definitions in 'definitions.txt'
      are only performed once, even if 'definitions.txt' is included
      multiple times.
"""

import re, os.path, textwrap
from optparse import OptionParser
from tree2image import tree_to_image

import docutils.core, docutils.nodes
from docutils.writers import Writer
from docutils.writers.html4css1 import HTMLTranslator, Writer as HTMLWriter
from docutils.writers.latex2e import LaTeXTranslator, Writer as LaTeXWriter
from docutils.parsers.rst import directives
import docutils.writers.html4css1

LATEX_VALIGN_IS_BROKEN = True
"""Set to true to compensate for a bug in the latex writer.  I've
   submitted a patch to docutils, so hopefully this wil be fixed
   soon."""

LATEX_DPI = 140
"""The scaling factor that should be used to display bitmapped images
   in latex/pdf output (specified in dots per inch).  E.g., if a
   bitmapped image is 100 pixels wide, it will be scaled to
   100/LATEX_DPI inches wide for the latex/pdf output.  (Larger
   values produce smaller images in the generated pdf.)"""

OUTPUT_FORMAT = None
"""A global variable, set by main(), indicating the output format for
   the current file.  Can be 'latex' or 'html'."""

OUTPUT_BASENAME = None
"""A global variable, set by main(), indicating the base filename
   of the current file (i.e., the filename with its extension
   stripped).  This is used to generate filenames for images."""

TREE_IMAGE_DIR = 'tree_images/'
"""The directory that tree images should be written to."""

######################################################################
#{ Directives
######################################################################

class example(docutils.nodes.paragraph): pass

def example_directive(name, arguments, options, content, lineno,
                      content_offset, block_text, state, state_machine):
    """
    Basic use::

        .. example:: John went to the store.

    To refer to examples, use::

        .. _store:
        .. example:: John went to the store.

        In store_, John performed an action.
    """
    text = '\n'.join(content)
    node = example(text)
    state.nested_parse(content, content_offset, node)
    return [node]
example_directive.content = True
directives.register_directive('example', example_directive)
directives.register_directive('ex', example_directive)

def doctest_directive(name, arguments, options, content, lineno,
                      content_offset, block_text, state, state_machine):
    """
    Used to explicitly mark as doctest blocks things that otherwise
    wouldn't look like doctest blocks.
    """
    text = '\n'.join(content)
    if re.match(r'.*\n\s*\n', block_text):
        print ('WARNING: doctest-ignore on line %d will not be ignored, '
               'because there is\na blank line between ".. doctest-ignore::"'
               ' and the doctest example.' % lineno)
    return [docutils.nodes.doctest_block(text, text)]
doctest_directive.content = True
directives.register_directive('doctest-ignore', doctest_directive)

_treenum = 0
def tree_directive(name, arguments, options, content, lineno,
		   content_offset, block_text, state, state_machine):
    global _treenum
    text = '\n'.join(arguments) + '\n'.join(content)
    _treenum += 1
    # Note: the two filenames generated by these two cases should be
    # different, to prevent conflicts.
    if OUTPUT_FORMAT == 'latex':
        density, scale = 300, 300
        scale = scale * options.get('scale', 100) / 100
        filename = '%s-tree-%s.pdf' % (OUTPUT_BASENAME, _treenum)
        align = LATEX_VALIGN_IS_BROKEN and 'bottom' or 'top'
    elif OUTPUT_FORMAT == 'html':
        density, scale = 100, 100
        density = density * options.get('scale', 100) / 100
        filename = '%s-tree-%s.png' % (OUTPUT_BASENAME, _treenum)
        align = 'top'
    else:
        assert 0, 'bad output format %r' % OUTPUT_FORMAT
    try:
        filename = os.path.join(TREE_IMAGE_DIR, filename)
        tree_to_image(text, filename, density)
    except ValueError, e:
        print 'Error parsing tree: %s\n%s' % (e, text)
        return [example(text, text)]

    imagenode = docutils.nodes.image(uri=filename, scale=scale, align=align)
    return [imagenode]

tree_directive.arguments = (1,0,1)
tree_directive.content = True
tree_directive.options = {'scale': directives.nonnegative_int}
directives.register_directive('tree', tree_directive)

def def_directive(name, arguments, options, content, lineno,
                  content_offset, block_text, state, state_machine):
    state_machine.document.setdefault('__defs__', {})[arguments[0]] = 1
def_directive.arguments = (1, 0, 0)
directives.register_directive('def', def_directive)
    
def ifdef_directive(name, arguments, options, content, lineno,
                    content_offset, block_text, state, state_machine):
    if arguments[0] in state_machine.document.get('__defs__', ()):
        node = docutils.nodes.compound('')
        state.nested_parse(content, content_offset, node)
        return list(node)
ifdef_directive.arguments = (1, 0, 0)
ifdef_directive.content = True
directives.register_directive('ifdef', ifdef_directive)
    
def ifndef_directive(name, arguments, options, content, lineno,
                    content_offset, block_text, state, state_machine):
    if arguments[0] not in state_machine.document.get('__defs__', ()):
        node = docutils.nodes.compound('')
        state.nested_parse(content, content_offset, node)
        return list(node)
ifndef_directive.arguments = (1, 0, 0)
ifndef_directive.content = True
directives.register_directive('ifndef', ifndef_directive)
    
    

######################################################################
#{ Figure & Example Numbering
######################################################################

class NumberingVisitor(docutils.nodes.NodeVisitor):
    """
    A transforming visitor that adds figure numbers to all figures,
    and converts any references to figures to use the text 'Figure #';
    and adds example numbers to all examples, and converts any
    references to examples to use the text 'Example #'.
    """
    LETTERS = 'abcdefghijklmnopqrstuvwxyz'
    ROMAN = 'i ii iii iv v vi vii viii ix x'.split()
    def __init__(self, document):
        self.figures = {}
        self.examples = {}
        self.figure_num = 1
        self.example_num = [0]
        docutils.nodes.NodeVisitor.__init__(self, document)
    def unknown_visit(self, node): pass
    def unknown_departure(self, node): pass

    def get_id(self, node):
        node_index = node.parent.children.index(node)
        if node_index>0 and isinstance(node.parent[node_index-1],
                                       docutils.nodes.target):
            target = node.parent[node_index-1]
            if target.has_key('refid'):
                refid = target['refid']
                target['ids'] = [refid]
                del target['refid']
                return refid
            elif target.has_key('ids'):
                return target['ids'][0]
            else:
                print 'unable to find id for %s' % target
                return None

    def visit_example(self, node):
        # Get the example number
        self.example_num[-1] += 1
        ex_num = str(self.example_num[0])
        if len(self.example_num) > 1:
            ex_num += self.LETTERS[self.example_num[1]-1]
        if len(self.example_num) > 2:
            ex_num += '.%s' % self.ROMAN[self.example_num[1]-1]
        for n in self.example_num[3:]:
            ex_num += '.%s' % n
        self.example_num.append(0)
            
        # Get the ID for the example, if it has one, & mark the
        # example with its number.
        node_id = self.get_id(node)
        if node_id: self.examples[node_id] = ex_num
        node['num'] = ex_num

    def depart_example(self, node):
        if self.example_num[-1] > 0:
            # If the example contains a list of subexamples, then
            # splice them in to our parent.
            node.replace_self(list(node))
        self.example_num.pop()
        
    def visit_figure(self, node):
        # Figure out our figure number, & update figure_num
        self.figure_num += 1
         
        # Get the ID for the figure, if it has one.
        node_id = self.get_id(node)
        if node_id: self.figures[node_id] = str(self.figure_num)

        # Mark the figure with its figure number.
        if isinstance(node[-1], docutils.nodes.caption):
            if OUTPUT_FORMAT == 'html':
                fig_num = docutils.nodes.Text("Figure %s: " % self.figure_num)
                node[-1].children.insert(0, fig_num)
        else:
            if OUTPUT_FORMAT == 'html':
                fig_num = docutils.nodes.Text("Figure %s" % self.figure_num)
                node.append(docutils.nodes.caption('', '', fig_num))
            else:
                node.append(docutils.nodes.caption()) # empty.
            
class ReferenceVisitor(docutils.nodes.NodeVisitor):
    def __init__(self, document, figures, examples):
        self.figures = figures
        self.examples = examples
        docutils.nodes.NodeVisitor.__init__(self, document)
    def unknown_visit(self, node): pass
    def unknown_departure(self, node): pass
        
    def visit_reference(self, node):
        node_id = node.get('refid')
        if node_id in self.figures:
            fig_num = "%s" % self.figures[node_id]
            node.children[:] = [docutils.nodes.Text(fig_num)]
        if node_id in self.examples:
            example_num = "(%s)" % self.examples[node_id]
            node.children[:] = [docutils.nodes.Text(example_num)]

def postprocess(document):
    v1 = NumberingVisitor(document)
    document.walkabout(v1)
    
    v2 = ReferenceVisitor(document, v1.figures, v1.examples)
    document.walkabout(v2)


######################################################################
#{ HTML Output
######################################################################

class CustomizedHTMLWriter(HTMLWriter):
    settings_defaults = HTMLWriter.settings_defaults.copy()
    settings_defaults.update({
        'stylesheet': '../nltkdoc.css',
        'stylesheet_path': None,
        'output_encoding': 'ascii',
        'output_encoding_error_handler': 'xmlcharrefreplace',
        })
        
    def __init__(self):
        HTMLWriter.__init__(self)
        self.translator_class = CustomizedHTMLTranslator

    def translate(self):
        postprocess(self.document)
        HTMLWriter.translate(self)

class CustomizedHTMLTranslator(HTMLTranslator):
    def visit_doctest_block(self, node):
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc)
        self.body.append(self.starttag(node, 'pre', CLASS='doctest-block'))
        self.body.append(pysrc)
        self.body.append('\n</pre>\n')
        raise docutils.nodes.SkipNode

    def depart_doctest_block(self, node):
        pass

    def visit_literal(self, node):
        """Process text to prevent tokens from wrapping."""
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc, True)
        self.body.append(
	    self.starttag(node, 'tt', '', CLASS='doctest'))
	self.body.append('<span class="pre">%s</span>' % pysrc)
        self.body.append('</tt>')
        # Content already processed:
        raise docutils.nodes.SkipNode
                          
    def _markup_pysrc(self, s, tag):
        return '<span class="pysrc-%s">%s</span>' % (tag, self.encode(s))

    def visit_example(self, node):
        self.body.append(
            '<p><table border="0" cellpadding="0" cellspacing="0">'
            '<tr valign="top"><td width="30" align="right">'
            '(%s)</td><td width="15"></td><td>' % node['num'])

    def depart_example(self, node):
        self.body.append('</td></tr></table></p>\n')


######################################################################
#{ LaTeX Output
######################################################################

class CustomizedLaTeXWriter(LaTeXWriter):
    settings_defaults = LaTeXWriter.settings_defaults.copy()
    settings_defaults.update({
        'output_encoding': 'utf-8',
        'output_encoding_error_handler': 'backslashreplace',
        'use_latex_docinfo': True,
        'font_encoding': 'C10,T1',
        'stylesheet': '../definitions.sty',
        'use_latex_footnotes': True,
        })
    
    def __init__(self):
        LaTeXWriter.__init__(self)
        self.translator_class = CustomizedLaTeXTranslator

    def translate(self):
        postprocess(self.document)
        LaTeXWriter.translate(self)
        
class CustomizedLaTeXTranslator(LaTeXTranslator):
    
    # Not sure why we need this, but the old Makefile did it so I will too:
    encoding = '\\usepackage[%s,utf8x]{inputenc}\n'
    
    def __init__(self, document):
        LaTeXTranslator.__init__(self, document)
        # This needs to go before the \usepackage{inputenc}:
        self.head_prefix.insert(1, '\\usepackage[cjkgb]{ucs}\n')
        # Make sure we put these *before* the stylesheet include line.
        self.head_prefix.insert(-2, textwrap.dedent("""\
            % For Python source code:
            \\usepackage{alltt}
            % Python source code: Prompt
            \\newcommand{\\pysrcprompt}[1]{\\textbf{#1}}
            \\newcommand{\\pysrcmore}[1]{\\textbf{#1}}
            % Python source code: Source code
            \\newcommand{\\pysrckeyword}[1]{\\textbf{#1}}
            \\newcommand{\\pysrcbuiltin}[1]{\\textbf{#1}}
            \\newcommand{\\pysrcstring}[1]{\\textit{#1}}
            \\newcommand{\\pysrcother}[1]{\\textbf{#1}}
            % Python source code: Comments
            \\newcommand{\\pysrccomment}[1]{\\textrm{#1}}
	    % Python interpreter: Traceback message
            \\newcommand{\\pysrcexcept}[1]{\\textbf{#1}}
            % Python interpreter: Output
            \\newcommand{\\pysrcoutput}[1]{#1}\n"""))

    def visit_doctest_block(self, node):
        self.literal = True
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc)
        self.literal = False
        self.body.append('\\begin{alltt}\n')
        self.body.append(pysrc)
        self.body.append('\\end{alltt}\n')
        raise docutils.nodes.SkipNode

    def depart_doctest_block(self, node):
        pass

    def visit_literal(self, node):
        self.literal = True
        pysrc = colorize_doctestblock(str(node[0]), self._markup_pysrc, True)
        self.literal = False
        self.body.append('\\texttt{%s}' % pysrc)
        raise docutils.nodes.SkipNode

    def depart_literal(self, node):
	pass

    def _markup_pysrc(self, s, tag):
        return '\\pysrc%s{%s}' % (tag, self.encode(s))

    def visit_image(self, node):
        """So image scaling manually"""
        # Images are rendered using \includegraphics from the graphicx
        # package.  By default, it assumes that bitmapped images
        # should be rendered at 72 DPI; but we'd rather use a
        # different scale.  So adjust the scale attribute & then
        # delegate to our parent class.
        node.attributes['scale'] = (node.attributes.get('scale', 100) *
                                    72.0/LATEX_DPI)
        return LaTeXTranslator.visit_image(self, node)
        
    def visit_example(self, node):
        self.body.append('\\begin{itemize}\n\item[(%s)] ' % node['num'])

    def depart_example(self, node):
        self.body.append('\\end{itemize}\n')
        
######################################################################
#{ Source Code Highlighting
######################################################################

# Regular expressions for colorize_doctestblock
# set of keywords as listed in the Python Language Reference 2.4.1
# added 'as' as well since IDLE already colorizes it as a keyword.
# The documentation states that 'None' will become a keyword
# eventually, but IDLE currently handles that as a builtin.
_KEYWORDS = """
and       del       for       is        raise    
assert    elif      from      lambda    return   
break     else      global    not       try      
class     except    if        or        while    
continue  exec      import    pass      yield    
def       finally   in        print
as
""".split()
_KEYWORD = '|'.join([r'\b%s\b' % _KW for _KW in _KEYWORDS])

_BUILTINS = [_BI for _BI in dir(__builtins__) if not _BI.startswith('__')]
_BUILTIN = '|'.join([r'\b%s\b' % _BI for _BI in _BUILTINS])

_STRING = '|'.join([r'("""("""|.*?((?!").)"""))', r'("("|.*?((?!").)"))',
                    r"('''('''|.*?[^\\']'''))", r"('('|.*?[^\\']'))"])
_COMMENT = '(#.*?$)'
_PROMPT1 = r'^\s*>>>(?:\s|$)'
_PROMPT2 = r'^\s*\.\.\.(?:\s|$)'

PROMPT_RE = re.compile('(%s|%s)' % (_PROMPT1, _PROMPT2),
		       re.MULTILINE | re.DOTALL)
PROMPT2_RE = re.compile('(%s)' % _PROMPT2, re.MULTILINE | re.DOTALL)
'''The regular expression used to find Python prompts (">>>" and
"...") in doctest blocks.'''

EXCEPT_RE = re.compile(r'(.*)(^Traceback \(most recent call last\):.*)',
                       re.DOTALL | re.MULTILINE)

DOCTEST_DIRECTIVE_RE = re.compile(r'#\s*doctest:.*')

DOCTEST_RE = re.compile(r"""(?P<STRING>%s)|(?P<COMMENT>%s)|"""
                        r"""(?P<KEYWORD>(%s))|(?P<BUILTIN>(%s))|"""
                        r"""(?P<PROMPT1>%s)|(?P<PROMPT2>%s)|.+?""" %
  (_STRING, _COMMENT, _KEYWORD, _BUILTIN, _PROMPT1, _PROMPT2),
  re.MULTILINE | re.DOTALL)
'''The regular expression used by L{_doctest_sub} to colorize doctest
blocks.'''

def colorize_doctestblock(s, markup_func, inline=False, strip_directives=True):
    """
    Colorize the given doctest string C{s} using C{markup_func()}.
    C{markup_func()} should be a function that takes a substring and a
    tag, and returns a colorized version of the substring.  E.g.:

        >>> def html_markup_func(s, tag):
        ...     return '<span class="%s">%s</span>' % (tag, s)

    The tags that will be passed to the markup function are: 
        - C{prompt} -- the Python PS1 prompt (>>>)
	- C{more} -- the Python PS2 prompt (...)
        - C{keyword} -- a Python keyword (for, if, etc.)
        - C{builtin} -- a Python builtin name (abs, dir, etc.)
        - C{string} -- a string literal
        - C{comment} -- a comment
	- C{except} -- an exception traceback (up to the next >>>)
        - C{output} -- the output from a doctest block.
        - C{other} -- anything else (does *not* include output.)
    """
    pysrc = [] # the source code part of a docstest block (lines)
    pyout = [] # the output part of a doctest block (lines)
    result = []
    out = result.append

    if strip_directives:
        s = DOCTEST_DIRECTIVE_RE.sub('', s)

    def subfunc(match):
        if match.group('PROMPT1'):
            return markup_func(match.group(), 'prompt')
	if match.group('PROMPT2'):
	    return markup_func(match.group(), 'more')
        if match.group('KEYWORD'):
            return markup_func(match.group(), 'keyword')
        if match.group('BUILTIN'):
            return markup_func(match.group(), 'builtin')
        if match.group('COMMENT'):
            return markup_func(match.group(), 'comment')
        if match.group('STRING') and '\n' not in match.group():
            return markup_func(match.group(), 'string')
        elif match.group('STRING'):
            # It's a multiline string; colorize the string & prompt
            # portion of each line.
            pieces = [markup_func(s, ['string','more'][i%2])
                      for i, s in enumerate(PROMPT2_RE.split(match.group()))]
            return ''.join(pieces)
        else:
            return markup_func(match.group(), 'other')

    if inline:
	pysrc = DOCTEST_RE.sub(subfunc, s)
	return pysrc.strip()

    # need to add a third state here for correctly formatting exceptions

    for line in s.split('\n')+['\n']:
        if PROMPT_RE.match(line):
            pysrc.append(line)
            if pyout:
                pyout = '\n'.join(pyout).strip()
                m = EXCEPT_RE.match(pyout)
                if m:
                    pyout, pyexc = m.group(1).strip(), m.group(2).strip()
                    if pyout:
                        print ('Warning: doctest does not allow for mixed '
                               'output and exceptions!')
                        result.append(markup_func(pyout, 'output'))
                    result.append(markup_func(pyexc, 'except'))
                else:
                    result.append(markup_func(pyout, 'output'))
                pyout = []
        else:
            pyout.append(line)
            if pysrc:
                pysrc = DOCTEST_RE.sub(subfunc, '\n'.join(pysrc))
                result.append(pysrc.strip())
                #result.append(markup_func(pysrc.strip(), 'python'))
                pysrc = []

    remainder = '\n'.join(pyout).strip()
    if remainder:
        result.append(markup_func(remainder, 'output'))
        
    return '\n'.join(result)

######################################################################
#{ Chapter numbering
######################################################################

# Add chapter numbers; docutils doesn't handle (multi-file) books
def chapter_numbers(out_file):
    f = open(out_file).read()
    # LaTeX
    c = re.search(r'pdftitle={(\d+)\. ([^}]+)}', f)
    if c:
        chnum = c.group(1)
        chtitle = c.group(2)
        f = re.sub(r'(pdfbookmark\[\d+\]{)', r'\g<1>'+chnum+'.', f)
        f = re.sub(r'(section\*{)', r'\g<1>'+chnum+'.', f)
        f = re.sub(r'(\\begin{document})',
                   r'\def\chnum{'+chnum+r'}\n' +
                   r'\def\chtitle{'+chtitle+r'}\n' +
                   r'\g<1>', f)
        open(out_file, 'w').write(f)
    # HTML
    c = re.search(r'<h1 class="title">(\d+)\.', f)
    if c:
        chapter = c.group(1)
        f = re.sub(r'(<h\d><a[^>]*>)', r'\g<1>'+chapter+'.', f)
        open(out_file, 'w').write(f)
    


######################################################################
#{ Main Script
######################################################################

__version__ = 0.1

def parse_args():
    optparser = OptionParser()

    optparser.add_option("--html", 
        action="store_const", dest="action", const="html",
        help="Write HTML output.")
    optparser.add_option("--latex", "--tex",
        action="store_const", dest="action", const="latex",
        help="Write LaTeX output.")

    optparser.set_defaults(action='html')

    options, filenames = optparser.parse_args()
    return options, filenames

def main():
    global OUTPUT_FORMAT, OUTPUT_BASENAME
    options, filenames = parse_args()

    if not os.path.exists(TREE_IMAGE_DIR):
        os.mkdir(TREE_IMAGE_DIR)

    if docutils.writers.html4css1.Image is None:
        print ('WARNING: Cannot scale images in HTML unless Python '
               'Imaging\n         Library (PIL) is installed!')

    OUTPUT_FORMAT = options.action
    if options.action == 'html':
        writer = CustomizedHTMLWriter()
        output_ext = '.html'
    elif options.action == 'latex':
        writer = CustomizedLaTeXWriter()
        output_ext = '.tex'
    else:
        assert 0, 'bad action'

    for in_file in filenames:
        OUTPUT_BASENAME = os.path.splitext(in_file)[0]
        out_file = os.path.splitext(in_file)[0] + output_ext
        if in_file == out_file: out_file += output_ext
        docutils.core.publish_file(source_path=in_file,
                                   destination_path=out_file,
                                   writer=writer)
        chapter_numbers(out_file)

if __name__ == '__main__':
    main()
