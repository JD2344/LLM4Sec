from xml.parsers import expat

class DisableXmlNamespaces:
    def __enter__(self):
            self.oldcreate = expat.ParserCreate
            expat.ParserCreate = lambda encoding, sep: self.oldcreate(encoding, None)
    def __exit__(self, type, value, traceback):
            expat.ParserCreate = self.oldcreate