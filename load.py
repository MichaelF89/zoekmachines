# whoosh imports
###############################################
from whoosh.index import create_in
from whoosh.index import open_dir
from whoosh.fields import *
from whoosh.qparser import QueryParser
from whoosh import qparser
from whoosh.scoring import WeightingModel
from whoosh.scoring import Weighting
from whoosh.scoring import PL2
from whoosh.scoring import BM25F
from whoosh.scoring import TF_IDF
from whoosh.scoring import Frequency

# tornado imports
##############################################
import tornado.httpserver
import tornado.ioloop
import tornado.web


# other imports
###############################################
import re
import os
import os.path
import shutil
import time
import random
import subprocess
from math import sqrt
from math import log
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt 

from pprint import pprint
import tagcloud

# program constants
###############################################
indexdir='index'
webdir='web'
search_file = webdir + '/search.html'
working_dir = os.environ["PWD"]


# This is the cosine implementation from whoosh 0.3
###############################################
class Cosine(Weighting):
    """A cosine vector-space scoring algorithm, translated into Python
    from Terrier's Java implementation.
    """

    def score(self, searcher, fieldnum, text, docnum, weight, QTF=1):
        idf = searcher.idf(fieldnum, text)

        DTW = (1.0 + log(weight)) * idf
        QMF = 1.0 # TODO: Fix this
        QTW = ((0.5 + (0.5 * QTF / QMF))) * idf
        return DTW * QTW


# Create the index
###############################################
def create_index(dir=indexdir, stemming=True, stopwords=None):
  if os.path.exists(dir):
    shutil.rmtree(dir)
  os.mkdir(dir)
  res = -1
  if stemming:
    if stopwords == None:
      res= subprocess.call(["python", "tools/scripts/preprocessing/whoosh_index.py", "-i", dir, "-w", "data/aggregated", "-s"])
    else: 
      res= subprocess.call(["python", "tools/scripts/preprocessing/whoosh_index.py", "-i", dir, "-w", "data/aggregated", "-s", "-r", stopwords])
  else:
    if stopwords == None:
      res= subprocess.call(["python", "tools/scripts/preprocessing/whoosh_index.py", "-i", dir, "-w", "data/aggregated"])
    else:
      res= subprocess.call(["python", "tools/scripts/preprocessing/whoosh_index.py", "-i", dir, "-w", "data/aggregated", "-r", stopwords])
     
  if (res != 0):
    raise Exception("Problem creating index!")


# opening the index
###############################################
index = open_dir(indexdir)

# instantiating three searcher objects
###############################################
searcher_bm25f = index.searcher(weighting=BM25F)
searcher_pl2 = index.searcher(weighting=PL2)
searcher_cosine = index.searcher(weighting=Cosine)
searcher_tf_idf = index.searcher(weighting=TF_IDF)
searcher_frequency = index.searcher(weighting=Frequency)

# reader 
###############################################
reader = index.reader()

# parsers
###############################################
parser_content = qparser.QueryParser("content")
parser_title = qparser.QueryParser("title")
parser = qparser.MultifieldParser(['content', 'title'])

# tornado request handlers
###############################################
class MainHandler(tornado.web.RequestHandler):
    def get(self):
        # read the html file on every request - very inefficient
        f = open(search_file, 'r')
        lines = f.readlines()
        for l in lines:
          self.write(l) 

class SearchHandler(tornado.web.RequestHandler):
    def post(self):
        query = self.get_argument("query")
        number = self.get_argument("number")
        scoring = self.get_argument("scoring")
        field = self.get_argument("field")
        searcher = None
        if scoring == "Cosine":
          searcher = application.searcher_cosine
        elif scoring == "PL2":
          searcher = application.searcher_pl2
        elif scoring == "BM25F":
          searcher = application.searcher_bm25f
        elif scoring == "TF_IDF":
          searcher = application.searcher_tf_idf
        elif scoring == "Frequency":
          searcher = application.searcher_frequency
        else:
          raise Exception("Unsupported scoring method")
        res = searcher.find(field, unicode(query), limit=int(number))
        self.write("Query: " + query)
        self.write("<br />")
        self.write("Max hits: " + number)
        self.write("<br />")
        self.write("Scoring " + scoring)
        self.write("<br />")
        self.write("Field " + field)
        self.write("<br /> <br />")
        self.write("Number of hits:  " + str(min(int(number), len(res))) + "<br />")
        for r in res:
          nextid = str(r['id'])
          nexttitle = r['title']
          self.write("<a href=/display?docid=" + nextid + ">"+ nexttitle +"</a><br />")

class DocumentDisplayer(tornado.web.RequestHandler):
    def get(self):
      docid=self.get_argument("docid")
      res = application.searcher_bm25f.find("id", unicode(docid))
      path = get_relative_path(res[0]['path'])
      f = open(path, "r")
      lines = f.readlines()
      for l in lines:
        self.write(l)
      #self.write(tagcloud.print_cloud(['word1', 'word2']))
      #self.write(tagcloud.print_cloud(get_term_freq_doc(docid)))
      searcher = application.searcher_frequency
      x = get_term_freq_doc(docid, searcher)
      pprint(x)
      p = tagcloud.make_cloud(x)
      self.write(p)

class LexiconDisplayer(tornado.web.RequestHandler):
    def get(self):
      self.post()
    def post(self):
      field = self.get_argument("field", default="title")
      sort_by = self.get_argument("sort_by", default="term")
      lex = application.reader.lexicon(field)
      list_terms = []
      for l in lex:
        list_terms.append((l,
           application.reader.doc_frequency("title", l), 
           application.reader.doc_frequency("content", l)))
      self.write("<h2>") 
      srtd=list_terms
      if (sort_by == "frequency_title"):
         srtd = sorted(list_terms, key = lambda x:x[1], reverse=True)
         self.write("<a href="+generate_term_cloud([(x[0], x[1]) for x in srtd], 150) + "> Tag cloud for the top 50 entries in the table - if it doesn't load immediately just spam \"refresh \" </a><br />")
         self.write("<a href="+ plot([x[1] for x in srtd])+ "> Term distribution plot. </a><br />")
      elif (sort_by == "frequency_content"):
         srtd = sorted(list_terms, key = lambda x:x[2], reverse=True)  
         self.write("<a href="+generate_term_cloud([(x[0], x[2]/100) for x in srtd], 150) + "> Tag cloud for the top 50 entries in the table - takes several seconds, just spam \"refresh \" </a><br />")
         self.write("<a href="+ plot([x[2] for x in srtd])+ "> Term distribution plot. </a><br />")
      else:
         self.write("<a href="+ plot([x[2] for x in list_terms])+ "> Term distribution plot. </a>")
       

      self.write("</h2>")
      self.write("<table border = \"1\">")
      self.write("<tr>")
      self.write("<td> # </td>")
      self.write("<td> <a href=/lexdisplay?field="+field+"&sort_by=term> Term </a> </td>")
      self.write("<td> <a href=/lexdisplay?field="+field+"&sort_by=frequency_title> frequency in field \"title\" </a> </td>")
      self.write("<td> <a href=/lexdisplay?field="+field+"&sort_by=frequency_content> frequency in field \"content\" </a> </td>")
      self.write("</tr>")
      
      for i in range(0, len(list_terms)):
        self.write("<tr>")
        self.write("<td>" + str(i) + " </td>")
        self.write("<td><a href=/termstat?term=" + srtd[i][0] + ">"+ srtd[i][0] +"</a></td>")
        self.write("<td>"+ str(srtd[i][1]) +"</td>")
        self.write("<td>"+ str(srtd[i][2]) +"</td>")
        self.write("</tr>")

class TermStatisticsDisplayer(tornado.web.RequestHandler):
    def get(self):
      term = self.get_argument("term")
      freq_cont = application.reader.doc_frequency("content", term)
      freq_titl = application.reader.doc_frequency("title", term)
      cont = application.searcher_frequency.find("content", term, limit=max(freq_cont, 1))
      titl = application.searcher_frequency.find("title", term, limit=max(freq_titl,1))

      self.write("<h1>" + term + "</h1><br />")      
      self.write("Frequency in titles: " + str(freq_titl) + "<br />")
      for t in titl:
        nextid = str(t['id'])
        nexttitle = t['title']
        self.write("<a href=/display?docid=" + nextid + ">"+ nexttitle +"</a><br />")
      self.write("<br />Frequency in content: " + str(freq_cont) +"<br />" )    
      for c in cont:
        nextid = str(c['id'])
        nexttitle = c['title']
        self.write("<a href=/display?docid=" + nextid + ">"+ nexttitle +"</a><br />")

class Closer(tornado.web.RequestHandler):
    def get(self):
      close_resources()

class Indexer(tornado.web.RequestHandler):
    def post(self):
      tempfile = "tempfilestop"
      f = open(tempfile, 'w')
      sw = self.get_argument("stopwords", default=" ")
      words = re.split("\s", sw)
      for i in range(0, len(words)):
        f.write(words[i] + " ")
      f.close()
      close_resources(application)
      shutil.rmtree(indexdir) 
      if(self.get_argument("stemming") == "yes"):
        create_index(application.indexdir, stemming=True, stopwords=tempfile)
      else:     
        create_index(application.indexdir, stemming=False, stopwords=tempfile)
      os.remove(tempfile)
 
      application.index = open_dir(application.indexdir)

      # instantiating three searcher objects
      ###############################################
      application.searcher_bm25f = application.index.searcher(weighting=BM25F)
      application.searcher_pl2 = application.index.searcher(weighting=PL2)
      application.searcher_cosine = application.index.searcher(weighting=Cosine)
      application.searcher_tf_idf = application.index.searcher(weighting=TF_IDF)
      application.searcher_frequency = application.index.searcher(weighting=Frequency)

      # reader 
      ###############################################
      application.reader = application.index.reader()

      # parsers
      ###############################################
      application.parser_content = qparser.QueryParser("content")
      application.parser_title = qparser.QueryParser("title")
      application.parser = qparser.MultifieldParser(['content', 'title'])

     
      self.write("<h1>Indexed!</h1>")

class ZipfPlotter(tornado.web.RequestHandler):
    def get(self):
      pass        
# tornado web application
###############################################
#settings = {"static_path" : "/home/bkovach1/nytimes_corpus/web"}
settings = {"static_path" : webdir}
application = tornado.web.Application([
    (r"/", MainHandler),
    (r"/search", SearchHandler),
    (r"/display", DocumentDisplayer),
    (r"/lexdisplay", LexiconDisplayer),
    (r"/close", Closer),
    (r"/index", Indexer),
    (r"/termstat", TermStatisticsDisplayer)
], **settings)
application.index = index
application.indexdir = indexdir
application.searcher_bm25f = searcher_bm25f
application.searcher_pl2 = searcher_pl2
application.searcher_cosine = searcher_cosine
application.searcher_tf_idf = searcher_tf_idf
application.searcher_frequency = searcher_frequency
application.reader = reader
application.parser_content = parser_content
application.parser_title = parser_title
application.parser = parser


# tornado http server
# you still have to do:
# http_server.listen(<some port number>)
# tornado.ioloop.IOLoop.instance().start()
###############################################
http_server = tornado.httpserver.HTTPServer(application)

# method to start the server on a specified port
###############################################
def start_server(port):
  http_server = tornado.httpserver.HTTPServer(application)
  http_server.listen(port)
  tornado.ioloop.IOLoop.instance().start()


# close resources
###############################################
def close_resources(application):
  application.index.close()
  application.reader.close()
  application.searcher_bm25f.close()
  application.searcher_pl2.close()
  application.searcher_cosine.close()
  application.searcher_tf_idf.close()
  application.searcher_frequency.close()


# utility methods
###############################################




#terms_list is a list of tuples. The first element of
#each tuple is a term. The second is a number (frequency.)
#return a link to a term cloud

def generate_term_cloud(terms_list, words):
  import fietstas_rest
  from fietstas_rest import Fietstas

  doc = ""
  terms = [x[0] for x in terms_list]
  weights = [x[1] for x in terms_list]  
  for i in range(0, min(words,len(terms))):
    for j in range(0, weights[i]):
      doc += (terms[i] + " ")
 
  f = Fietstas(key='demo-key') 
  doc_id = f.upload_document(document = doc)
  cloud_link, cloud = f.make_cloud(docs=doc_id, words = words)
  return cloud_link 

# plots and returns a link to the plotted file
def plot(weights_list):
  plt.clf()
  #plt.plot(range(0, len(weights_list)), weights_list, 'ro')
  plt.loglog(range(0, len(weights_list)), weights_list, 'ro')
  plt.xlabel('Rank')
  plt.ylabel('Frequency')
  plt.savefig("web/plot.png")  
  return "/static/plot.png"

def get_relative_path(path):
  parts = re.split("\.\.\/", path)
  return parts[len(parts)-1]

def display(generator):
  for i in generator:
    print i

def get_term_freq_query(query):
   terms = re.split("\s", query)
   term_freq ={}
   for t in terms:
     if t in term_freq:
       term_freq[t] += 1
     else:
       term_freq[t] = 1
   return term_freq
 
def get_term_freq_doc(docid, searcher):
   docnum = searcher.document_number(id=docid)
   freq_generator = searcher.vector_as("frequency", docnum, "content")
   term_freq = {}
   for t in freq_generator:
     term_freq[t[0]] = t[1]
   return term_freq

def get_term_freq_col():
   lexicon  = reader.lexicon('content')
   term_freq = {}
   for l in lexicon:
     freq = reader.doc_frequency('content', l)
     term_freq[l] = freq
   return term_freq   

# Cosine similarity between a document and a query
def compute_cosine(docid, query):
   term_freq_query = get_term_freq_query(query)
   term_freq_doc = get_term_freq_doc(docid) 
   return _cosine(term_freq_query, term_freq_doc)  

def _cosine(x, y):
  # always compare the longest document against the shortest
    if len(x) < len(y):
      a = x
      x = y
      y = a
      del a
    xsum  = sum([k*k for k in x.values()])
    ysum  = sum([k*k for k in y.values()])  
    score = 0
    for word in x.iterkeys():
      if word not in y: 
        continue
      score += x[word]*y[word]
    score = score / sqrt(xsum*ysum)
        
    print "cosine similarity: %.2f" % score
    return score
  
