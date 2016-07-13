#!/usr/bin/env python

import time
import sys
from mitmproxy.script import concurrent
from mitmproxy.models import decoded

from geojson import GeometryCollection, Point, Feature, FeatureCollection
import geojson

import site
site.addsitedir("/usr/local/Cellar/protobuf/3.0.0-beta-3/libexec/lib/python2.7/site-packages")
sys.path.append("/usr/local/lib/python2.7/site-packages")
sys.path.append("/usr/local/Cellar/protobuf/3.0.0-beta-3/libexec/lib/python2.7/site-packages")
import numpy
import math
from google.protobuf.internal import enum_type_wrapper

from protocol.map_pb2 import *
from protocol.rpc_pb2 import *
from protocol.fortdetails_pb2 import *

associate = {} #Match responses to their requests
pokeLocation = {}
requests = {}

def triangulate((LatA, LonA, DistA), (LatB, LonB, DistB), (LatC, LonC, DistC)):
  #using authalic sphere
  #if using an ellipsoid this step is slightly different
  #Convert geodetic Lat/Long to ECEF xyz
  #   1. Convert Lat/Long to radians
  #   2. Convert Lat/Long(radians) to ECEF
  earthR = 6371
  xA = earthR *(math.cos(math.radians(LatA)) * math.cos(math.radians(LonA)))
  yA = earthR *(math.cos(math.radians(LatA)) * math.sin(math.radians(LonA)))
  zA = earthR *(math.sin(math.radians(LatA)))

  xB = earthR *(math.cos(math.radians(LatB)) * math.cos(math.radians(LonB)))
  yB = earthR *(math.cos(math.radians(LatB)) * math.sin(math.radians(LonB)))
  zB = earthR *(math.sin(math.radians(LatB)))

  xC = earthR *(math.cos(math.radians(LatC)) * math.cos(math.radians(LonC)))
  yC = earthR *(math.cos(math.radians(LatC)) * math.sin(math.radians(LonC)))
  zC = earthR *(math.sin(math.radians(LatC)))

  P1 = numpy.array([xA, yA, zA])
  P2 = numpy.array([xB, yB, zB])
  P3 = numpy.array([xC, yC, zC])

  #from wikipedia
  #transform to get circle 1 at origin
  #transform to get circle 2 on x axis
  ex = (P2 - P1)/(numpy.linalg.norm(P2 - P1))
  i = numpy.dot(ex, P3 - P1)
  ey = (P3 - P1 - i*ex)/(numpy.linalg.norm(P3 - P1 - i*ex))
  ez = numpy.cross(ex,ey)
  d = numpy.linalg.norm(P2 - P1)
  j = numpy.dot(ey, P3 - P1)

  #from wikipedia
  #plug and chug using above values
  x = (pow(DistA,2) - pow(DistB,2) + pow(d,2))/(2*d)
  y = ((pow(DistA,2) - pow(DistC,2) + pow(i,2) + pow(j,2))/(2*j)) - ((i/j)*x)

  # only one case shown here
  z = numpy.sqrt(pow(DistA,2) - pow(x,2) - pow(y,2))

  #triPt is an array with ECEF x,y,z of trilateration point
  triPt = P1 + x*ex + y*ey + z*ez

  #convert back to lat/long from ECEF
  #convert to degrees
  lat = math.degrees(math.asin(triPt[2] / earthR))
  lon = math.degrees(math.atan2(triPt[1],triPt[0]))

  return(str(lat) + "," + str(lon))

@concurrent  # Remove this and see what happens
def request(context, flow):
  if flow.match("~d pgorelease.nianticlabs.com"):
    env = RpcRequestEnvelopeProto()
    env.ParseFromString(flow.request.content)
    key = env.parameter[0].key
    value = env.parameter[0].value

    associate[env.request_id] = key

    if (key == GET_MAP_OBJECTS):
      mor = MapObjectsRequest()
      mor.ParseFromString(value)
      print(mor)
      requests[env.request_id] = (env.lat,env.long)
      print("Requests are:")
      print(requests)
    elif (key == FORT_DETAILS):
      mor = FortDetailsProto()
      mor.ParseFromString(value)
      print(mor)
    elif (key == FORT_SEARCH):
      mor = FortSearchProto()
      mor.ParseFromString(value)
      print(mor)
    elif (key == GET_GYM_DETAILS):
      mor = FortDetailsProto()
      mor.ParseFromString(value)
      print(mor)
    else:
      print("API: %s" % key)

def response(context, flow):
  with decoded(flow.response):
    if flow.match("~d pgorelease.nianticlabs.com"):
      env = RpcResponseEnvelopeProto()
      env.ParseFromString(flow.response.content)
      key = associate[env.response_id]
      value = env.returns[0]

      if (key == GET_MAP_OBJECTS):
        mor = MapObjectsResponse()
        mor.ParseFromString(value)
        print("GET_MAP_OBJECTS %i tiles" % len(mor.tiles))
        features = []

        for tile in mor.tiles:
          print("S2 Cell %i" % tile.id)
          for fort in tile.forts:
            p = Point((fort.longitude, fort.latitude))
            if fort.is_pokestop:
              f = Feature(geometry=p, id=len(features), properties={"id": fort.id, "tile": tile.id, "type": "fort", "marker-color": "00007F", "marker-symbol": "town-hall"})
              features.append(f)
            else:
              f = Feature(geometry=p, id=len(features), properties={"id": fort.id, "tile": tile.id, "type": "fort", "marker-color": "0000FF", "marker-symbol": "town-hall", "marker-size": "large"})
              features.append(f)

          for fort in tile.location4:
            p = Point((fort.longitude, fort.latitude))
            f = Feature(geometry=p, id=len(features), properties={"tile": tile.id, "type": "location4", "marker-color": "FFFF00", "marker-symbol": "monument"})
            features.append(f)

          for fort in tile.location9:
            p = Point((fort.longitude, fort.latitude))
            f = Feature(geometry=p, id=len(features), properties={"tile": tile.id, "type": "location9", "marker-color": "00FFFF"})
            features.append(f)


          #Make into a line
          for fort in tile.spawn_start:
            p = Point((fort.longitude, fort.latitude))
            f = Feature(geometry=p, id=len(features), properties={"id": fort.uid, "tile": tile.id, "type": "close_pokemon_a", "marker-color": "FF0000", "marker-symbol": "circle-stroked"})
            features.append(f)

          for fort in tile.spawn_end:
            p = Point((fort.longitude, fort.latitude))
            f = Feature(geometry=p, id=len(features), properties={"id": fort.uid, "tile": tile.id, "type": "close_pokemon_b", "marker-color": "00FF00", "marker-symbol": "circle"})
            features.append(f)

          for poke in tile.pokemon_in_area:
            gps = requests[env.response_id]
            print(poke.distance)
            if poke.id in pokeLocation:
              if gps[0] != pokeLocation[poke.id][0][0]:
                pokeLocation[poke.id].append((gps[0], gps[1], poke.distance/1000))
            else:
              pokeLocation[poke.id] = [(gps[0], gps[1], poke.distance/1000)]
            print(pokeLocation[poke.id])
            if len(pokeLocation[poke.id]) >= 3:
              print("Got three values")
              print(poke.pokedex)
              try:
                nums = triangulate(pokeLocation[poke.id][0],pokeLocation[poke.id][1],pokeLocation[poke.id][2])
                print nums
              except Exception as inst:
                print type(inst)
                print inst.args
                print inst

        fc = FeatureCollection(features)
        dump = geojson.dumps(fc, sort_keys=True)
        f = open('ui/get_map_objects.json', 'w')
        f.write(dump)
      elif (key == FORT_DETAILS):
        mor = FortDetailsOutProto()
        mor.ParseFromString(value)
        print(mor)
      elif (key == FORT_SEARCH):
        mor = FortSearchOutProto()
        mor.ParseFromString(value)
        print(mor)
      else:
        print("API: %s" % key)


