#!/usr/bin/env python

import os
import sys
import time
import datetime
import json

import pytz
import requests

MAILQUEUE_DIR = '/maildir'
LOG_DIR = '/logs'

REQUIRED_ENVIRON = [
  'MAILQUEUE_TO',
  'MAPBOX_TOKEN',
  'LONLAT_WORK',
  'LONLAT_HOME',
]

WORKDAYS = [1, 2, 3, 4, 5]
TIMERS = [
  {'hour': 16, 'minute': 30},
  {'hour': 16, 'minute': 40},
  {'hour': 16, 'minute': 50},
]

MAIL_THRESHOLD = 40 * 60

def set_timer():
  now = datetime.datetime.now().astimezone(tz=pytz.timezone('Europe/Amsterdam'))

  for t in TIMERS:
    t_dt = now.replace(**t)

    diff = (t_dt - now).total_seconds()
    if diff > 0:
      time.sleep(diff)
      return

  t_dt = now + datetime.timedelta(days=1)
  t_dt = t_dt.replace(**t)

  diff = (t_dt - now).total_seconds()
  time.sleep(diff)

def mail_result(subject, msg):
  dst = os.environ['MAILQUEUE_TO']
  mail_path = os.path.join(os.path.expanduser(MAILQUEUE_DIR), f'traffic_{int(time.time())}')
  with open(mail_path, 'x') as fp:
    fp.write(f'{dst}\n')
    fp.write(f'traffic - {subject}\n')
    fp.write(f'<html><pre>{msg}</pre></html>')

def log(line, fn='out.log'):
  path = os.path.join(os.path.dirname(__file__), LOG_DIR, fn)
  with open(path, 'a') as f:
    f.write(line)

def api_request(coordinates):
  url = 'https://api.mapbox.com/directions/v5/mapbox/driving-traffic/'
  url += ';'.join([','.join([str(x) for x in coords]) for coords in coordinates])
  url += '?access_token=' + os.environ['MAPBOX_TOKEN']
  url += '&alternatives=true'
  url += '&annotations=distance,duration,congestion_numeric,closure'
  url += '&overview=full'
  url += '&geometries=geojson'

  resp = requests.get(url)

  if resp.status_code != 200:
    raise Exception(f'Failed api request: {resp.status_code}, {resp.text}')

  json_ = resp.json()
  return json_['routes']

def filter_route(r):
  res = {}

  res['duration'] = r['duration']
  res['duration_typical'] = r['duration_typical']
  res['distance'] = r['distance']

  assert len(r['legs']) == 1
  assert len(r['geometry']['coordinates']) == len(r['legs'][0]['annotation']['congestion_numeric']) + 1

  res['summary'] = r['legs'][0]['summary']
  res['incidents'] = r['legs'][0].get('incidents', [])
  res['closures'] = r['legs'][0].get('closures', [])

  return res

def direction_routes(start, end):
  routes = api_request([start, end])

  route = routes[0]
  route_alt = None
  if len(routes) > 1:
    route_alt = routes[1]
    if routes[0]['duration'] > routes[1]['duration']:
      route, route_alt = route_alt, route

  return filter_route(route)

def main():
  work = tuple([float(x) for x in os.environ['LONLAT_WORK'].split(',')])
  home = tuple([float(x) for x in os.environ['LONLAT_HOME'].split(',')])

  last_mailed_day = None
  while True:
    set_timer()

    now = datetime.datetime.now().astimezone(tz=pytz.timezone('Europe/Amsterdam'))
    if now.isoweekday() not in WORKDAYS:
      continue

    today = now.date()
    if last_mailed_day == today:
      continue

    try:
      entry = direction_routes(work, home)
    except Exception as e:
      mail_result('failed', str(e))
      print(e)
      continue

    entry.update({
      'departure': now.isoformat(),
      'isoweekday': now.isoweekday(),
      'hour': now.hour,
      'minute': now.minute,
    })

    res = json.dumps(entry)

    log(res + '\n', 'alert.log')

    if entry['duration'] > MAIL_THRESHOLD:
      msg = json.dumps(entry, indent=4)
      mail_result('alert', msg)

      last_mailed_day = today

if __name__ == '__main__':
  for req in REQUIRED_ENVIRON:
    ok = True
    if req not in os.environ:
      print(f"Missing environment variable '{req}'")
      ok = False

  if not ok:
    return

  if 'UMASK' in os.environ:
    os.umask(int(os.environ['UMASK'], 8))

  main()

