.. Sygaldry documentation master file, created by
   sphinx-quickstart on Thu May 27 18:34:15 2021.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

========
Sygaldry
========

Sygaldry


Config is parsed in distinct steps:

#. First all files, including any additional files and included files are parsed as strings.
#. Then Jinja templating is applied to the strings.
#. Finally the string with the variables applied is parsed as YAML.

Artificery
==========

In the Kingkiller Chronicles the Artificery is an enormous workshop inside the University.
It is the place where Sygaldry is used to create amazing objects.

.. automodule:: sygaldry.artificery
   :members:


.. toctree::
   :maxdepth: 2
   :caption: Contents:




Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
