#
# This tool joins an polygon shapefile to a Cube network, adding a field from
# the shapefile to the Cube network.
#
# Create by lmz 9/18/2014.
#
# Uses 
# * fiona (http://toblerity.org/fiona) to read shapefiles
# * shapely (http://toblerity.org/shapely) to perform shape calcs
# * GDAL (required by fiona) and VCredist SP1
#
# (Note: I installed all of these from http://www.lfd.uci.edu/~gohlke/pythonlibs/)
#
USAGE = """

  python attachShapeToNetwork.py -s shp_fieldname1 [-s shp_fieldname2...]
      -c cube_fieldname1 [-c cube_fieldname2 ...] freeflow.net shapefile.shp  freeflow_out.net
  
  Takes the Cube file, freeflow.net, and attaches the polygon shapefile, shapefile.shp,
  which has the field(s) shp_fieldname1 (shp_fieldname2, ...)
  
  Note: the polygon shapefile should be in the same coordinate system as the Cube file.
  
  Outputs a similar Cube file, freeflow_out.net, which has the additional field added
  to each link.  The new field(s) is given by cube_fieldname1 (cube_fieldname2, ...)
 
  The location of Cube's runtpp.exe should be in your path.
  
"""

import csv
import fiona  # requires gdal and vcredist_x64.exe
import getopt
import logging
import os
import pprint
import shapely.geometry
import shutil
import subprocess
import sys
import tempfile
import traceback

CUBE_EXPORT_SCRIPT_NAME = "cube_export.s"
CUBE_EXPORT_SCRIPT = r"""
; script generated by attachShapeToNetwork.py
RUN PGM=NETWORK
 FILEI NETI[1]="%s"
 FILEO NODEO=%s,FORMAT=SDF,INCLUDE=N,X,Y
 FILEO LINKO=%s,FORMAT=SDF,INCLUDE=A,B
ENDRUN
"""

CUBE_JOINCOLS_SCRIPT_NAME = "cube_joincols.s"
CUBE_JOINCOLS_SCRIPT = r"""
; script generated by attachShapeToNetwork.py
RUN PGM=NETWORK
 FILEI NETI[1]  ="%s"
 FILEI LINKI[2] ="%s" VAR=A,B%s
 FILEO NETO     ="%s"
 MERGE RECORD=FALSE ; if the newcols added bad links, ignore them
ENDRUN
"""

def runCubeScript(tempdir, script_filename):
    """
    Run the cube script specified in the tempdir specified.
    Returns the return code.
    """
    # run it
    proc = subprocess.Popen("runtpp %s" % script_filename, cwd=tempdir, 
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for line in proc.stdout:
        line = line.strip('\r\n')
        logger.info("  stdout: " + line)
    for line in proc.stderr:
        line = line.strip('\r\n')
        logger.info("  stderr: " + line)
    retcode = proc.wait()
    if retcode == 2:
        raise Exception("Failed to run Cube script %s" % (script_filename))
    logger.info("Received %d from 'runtpp %s'" % (retcode, script_filename))
    
def readCubeNetwork(filename):
    """
    Reads the Cube network specified by the given filename.
    
    Returns a list of (shapely.LineStrings instances, a, b) 
    """
    # get the tail of the filename to use for the intermediate files
    filename = os.path.abspath(filename)
    (head,tail) = os.path.split(filename)
    # strip the suffix
    if tail.find(".") >= 0:
        tail = tail[:tail.find(".")]
    nodes_filename = "%s_nodes.csv" % tail
    links_filename = "%s_links.csv" % tail
    
    tempdir = tempfile.mkdtemp()
    script_filename = os.path.join(tempdir, CUBE_EXPORT_SCRIPT_NAME)    

    # write the script file
    script_file = open(script_filename, "w")
    script_file.write(CUBE_EXPORT_SCRIPT % (filename, nodes_filename, links_filename))
    script_file.close()
    logger.info("Wrote %s" % script_filename)

    runCubeScript(tempdir, script_filename)
    
    # read the node csv into { n->(x,y) }
    nodes = {}
    nodes_file = open(os.path.join(tempdir, nodes_filename), 'rb')
    reader = csv.reader(nodes_file)
    for row in reader:
        nodes[int(row[0])] = (float(row[1]), float(row[2]))
    nodes_file.close()
    
    # read the link csv and create LineStrings
    linestrings = []
    links_file = open(os.path.join(tempdir, links_filename), 'rb')
    reader = csv.reader(links_file)
    row_num = 1
    for row in reader:
        a = int(row[0])
        b = int(row[1])
        if row_num < 6:
            logger.debug("row %d: A = %5d (%f, %f)," %
                (row_num, a, nodes[a][0], nodes[a][1]))
            logger.debug("       B = %5d (%f, %f)" % 
                (         b, nodes[b][0], nodes[b][1]))
        linestrings.append( (shapely.geometry.LineString([(nodes[a][0], nodes[a][1]),
                                                          (nodes[b][0], nodes[b][1])]), a, b) )
        row_num += 1
        
    links_file.close()
    logger.info("Read %d links from %s" % (len(linestrings), filename))
    
    # clean up tempdir
    logger.info("Deleting %s" % tempdir)
    shutil.rmtree(tempdir)
    
    return linestrings
    
def readShapefile(filename, shp_fieldnames):
    """
    Reads shapefile.
    
    Returns two items: 
     - a list of field types for the shp_fieldnames, and 
     - a list of [shapely.Polygon OR shapely.MutliPolygon instances, 
                  shp_fieldname1 value, 
                  shp_fieldname2 value, ...]
    """
    fi_reader = fiona.open(filename)
    
    shp_fieldtypes = []
    # make sure the required fields are in the schema
    for sf_idx in range(len(shp_fieldnames)):
        assert shp_fieldnames[sf_idx] in fi_reader.schema['properties']
        shp_fieldtypes.append(fi_reader.schema['properties'][shp_fieldnames[sf_idx]])

    shape_data = []
    cleaned = 0
    for shape_idx in range(len(fi_reader)):
        rec = next(fi_reader)
        tuple = []
        
        geom = shapely.geometry.shape(rec['geometry'])
        if not geom.is_valid:
            clean = geom.buffer(0.0)
            assert clean.is_valid
            geom = clean
            cleaned += 1
        tuple.append( geom )
        
        for sf_idx in range(len(shp_fieldnames)):
            tuple.append( rec['properties'][shp_fieldnames[sf_idx]] )
        shape_data.append(tuple)

    logger.info("Read %d shapes from %s, cleaned %d" % (len(shape_data), filename, cleaned))
    return shp_fieldtypes, shape_data
    
def joinCubeLinksToShapes(cube_linestrings, shapefile_data):
    """
    cube_linstrings is a list of shapely.LineStrings
    
    shapefile_data is a list of (shapely.Polygon instances, shp_fieldname values)
    
    Returns a dictionary { cube_linestring index -> shapefile_data index },
    mapping cube_linestrings with the relevant shapefile data.
    
    """
    # let's see where we are.
    # make a list of indices which contain the linestring
    line_to_shapeidx = {}
    for link_idx in range(len(cube_linestrings)):
        linestring_tuple  = cube_linestrings[link_idx]
        linestring        = linestring_tuple[0]
        maxintline_len    = -1.0
        maxintline_idx    = -1
        linestring_length = linestring.length

        containers = []
        for idx in range(len(shapefile_data)):
            polygon = shapefile_data[idx][0]
            
            # check bounds first - don't waste time
            if linestring.bounds[0] > polygon.bounds[2]: continue  # min > max
            if linestring.bounds[1] > polygon.bounds[3]: continue
            if linestring.bounds[2] < polygon.bounds[0]: continue  # max < min
            if linestring.bounds[3] < polygon.bounds[1]: continue
            
            if polygon.contains(linestring):
                maxintline_idx = idx
                maxintline_len = linestring_length
                break
                
            try:
                intline = polygon.intersection(linestring)
                if intline.length >= 0 and intline.length > maxintline_len:
                    maxintline_len = intline.length
                    maxintline_idx = idx
                    
            except shapely.geos.TopologicalError:
                # no intersection
                pass
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_traceback,
                                          file=sys.stdout)
        
        # print out if nothing found
        if maxintline_idx == -1:
            logger.warn("No match found for linestring %5d - %5d" %
                (linestring_tuple[1], linestring_tuple[2]))

        # save it in the result dictionary
        line_to_shapeidx[link_idx] = maxintline_idx
        
        if link_idx > 0 and link_idx % 100 == 0:
            logger.info("Processed %7d links" % link_idx)

    return line_to_shapeidx

def writeCubeNetworkWithNewCols(cubenet_infilename, cube_linestrings, line_to_shapeidx, 
                                shapefile_data, shp_fieldnames, shp_fieldtypes,
                                cube_outfilename):
    """
    Creates the cube network with the new columns.
    
    Does so by creating output file with the new columns and running a cube script to read it.
    """
    tempdir = tempfile.mkdtemp()
        
    # Write output file with new columns
    cubenet_infilename = os.path.abspath(cubenet_infilename)
    (head,tail) = os.path.split(cubenet_infilename)
    if tail.find(".") >= 0: tail = tail[:tail.find(".")] # strip the suffix
    
    newcol_filename = "%s_newcols.txt" % tail
    newcol_filename = os.path.join(tempdir, newcol_filename)
    newcol_file = open(newcol_filename, 'w')
    for link_idx,shape_idx in line_to_shapeidx.iteritems():
        # a,b,
        newcol_file.write("%d,%d" % 
            (cube_linestrings[link_idx][1], cube_linestrings[link_idx][2]))
        # remainder
        for sf_idx in range(len(shp_fieldnames)):
            # quote strings
            if shp_fieldtypes[sf_idx][:3] == "str":
                newcol_file.write(',"%s"' % shapefile_data[shape_idx][sf_idx+1])                
            else:
                newcol_file.write(",%s" % shapefile_data[shape_idx][sf_idx+1])
        newcol_file.write("\n")
    newcol_file.close()
    logger.info("Wrote %d new columns to %s" % (len(line_to_shapeidx), newcol_filename))
    
    # Have cube script put them together
    script_filename = os.path.join(tempdir, CUBE_JOINCOLS_SCRIPT_NAME)
    cube_outfilename = os.path.abspath(cube_outfilename)
    varlist = ""
    for sf_idx in range(len(shp_fieldnames)):
        varlist = varlist + "," + shp_fieldnames[sf_idx]
        if shp_fieldtypes[sf_idx][:3] == "str": varlist = varlist + "(C)"
        
    # write the script file
    script_file = open(script_filename, "w")
    script_file.write(CUBE_JOINCOLS_SCRIPT % (cubenet_infilename, newcol_filename, 
        varlist, cube_outfilename))
    script_file.close()
    logger.info("Wrote %s" % script_filename)

    # run it
    runCubeScript(tempdir, script_filename)

    # clean up tempdir
    logger.info("Deleting %s" % tempdir)
    shutil.rmtree(tempdir)
    
if __name__ == '__main__':
    logger = logging.getLogger('attachShapeToNetwork')
    consolehandler = logging.StreamHandler()
    consolehandler.setLevel(logging.DEBUG)
    consolehandler.setFormatter(logging.Formatter('%(asctime)-15s %(name)-12s: %(levelname)-8s %(message)s', datefmt='%d %b %Y %H:%M:%S'))
    logger.addHandler(consolehandler)
    logger.setLevel(logging.DEBUG)

    optlist, args = getopt.getopt(sys.argv[1:], 'c:s:')
     
    if len(args) != 3:
        logger.fatal(USAGE)
        sys.exit(2)
    
    SHAPE_FIELDS = []
    CUBE_FIELDS  = []
    for o,a in optlist:
        if o=="-s":
            SHAPE_FIELDS.append(a)
        elif o=="-c":
            CUBE_FIELDS.append(a)
            
    if len(SHAPE_FIELDS) != len(CUBE_FIELDS):
        logger.fatal("Mismatching number of shape fileds (%s) and cube fields (%s)" % 
            (str(SHAPE_FIELDS), str(CUBE_FIELDS)))
        logger.fatal(USAGE)
        sys.exit(2)
        
    CUBENET_INFILE  = args[0]
    SHAPE_INFILE    = args[1]
    CUBENET_OUTFILE = args[2]
     
    cube_linestrings                 = readCubeNetwork(CUBENET_INFILE)
    shp_fieldtypes, shapefile_data   = readShapefile(SHAPE_INFILE, SHAPE_FIELDS)
    
    line_to_shapeidx = joinCubeLinksToShapes(cube_linestrings, shapefile_data)
    
    writeCubeNetworkWithNewCols(CUBENET_INFILE, cube_linestrings, line_to_shapeidx, 
                                shapefile_data, SHAPE_FIELDS, shp_fieldtypes,
                                CUBENET_OUTFILE)