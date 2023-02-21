#!/usr/bin/env python3

import logging
import os
import signal
import requests

from apscheduler.schedulers.background import BlockingScheduler, BackgroundScheduler
from datetime import datetime
from urllib.parse import urlparse, urlunparse
from requests.auth import HTTPBasicAuth
import json
import re

from ybparse import parse

DEFAULT_TRACCAR_HOST = 'http://traccar:8082'
DEFAULT_TRACCAR_KEYWORD = 'yb'
DEFAULT_TRACCAR_INTERVAL = 60
DEFAULT_YB_INTERVAL = 60

LOGGER = logging.getLogger(__name__)

# id from https://yb.tl/Simple/[expedition]

class YB2Traccar():
    def __init__(self, conf: dict):
        # Initialize the class.
        super().__init__()
        
        self.TraccarHost = conf.get("TraccarHost")
        self.TraccarUser = conf.get("TraccarUser")
        self.TraccarPassword = conf.get("TraccarPassword")
        self.TraccarKeyword = conf.get("TraccarKeyword")
        self.TraccarOsmand = conf.get("TraccarOsmand")
        self.TraccarInterval = conf.get("TraccarInterval")
        self.YBInterval = conf.get("YBInterval")

        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

        self.historydict = {}
        self.filterdict = {}

    
    def poll(self):
        page = requests.get(self.TraccarHost + "/api/devices?all=true", auth = HTTPBasicAuth(self.TraccarUser, self.TraccarPassword))
        if page.status_code != 200:
            LOGGER.info("Traccar auth failed")
            return

        filterdict={}
        for j in json.loads(page.content):
            # print(json.dumps(j, indent=2))
            if not j["disabled"]:
                attributes = j["attributes"]

                for att, value in attributes.items():
                    if re.search("^" + self.TraccarKeyword + "[0-9]{0,1}$", att.lower()):
                        ybattr = value.strip()
                        if re.search("^[A-Za-z0-9]* [0-9]*$", ybattr):
                            unid = j["uniqueId"]
                            ybexp, ybboat = ybattr.split(" ")

                            filterdict.setdefault(ybexp.lower(), {}).setdefault(ybboat, []).append(unid)

        self.filterdict = filterdict
        LOGGER.debug(f"Attributes: {filterdict}")

        filterjobs =[x.id for x in self.scheduler.get_jobs()]
        LOGGER.debug(f"Jobs: {filterjobs}")

        for filter in filterjobs:
            #delete old jobs
            if not filter in filterdict:
                LOGGER.debug(f"Job removed: {filter}")
                self.scheduler.remove_job(filter)

        for filter in filterdict:
            # check if it's running
            if not filter in filterjobs:
                LOGGER.debug(f"Job added: {filter}")
                self.scheduler.add_job(self.getyb, 'interval', args=[filter], next_run_time=datetime.now(), seconds=self.YBInterval, name=filter, id=filter)

    


    def getyb(self, *args):
        filter = args[0]

        LOGGER.debug("Getting YB Positions of %s" % filter)
        
        # getting position
        url = "https://yb.tl/BIN/%s/LatestPositions3" % filter
        r = requests.get(url)
        mybytearray=r.content

        # with open("LatestPositions3.4", 'rb') as f:
        #     mybytearray = bytearray(f.read())

        result = parse(mybytearray)

        for boatid in self.filterdict.get(filter):
            msgarr = [x['moments'] for x in result if x['id'] == int(boatid)][0]
            if not msgarr:
                continue

            msg = msgarr[0]
            lpos = msg['at']

            #if timestamp is duplicated skip it
            if lpos == self.historydict.get(filter, {}).get(boatid):
                logging.debug(f"Duplicate timestamp: {filter} {boatid} {lpos}")
                continue

            self.historydict.setdefault(filter, {})[boatid] = lpos

            lat = msg['lat']
            lon = msg['lon']
            speed = 0
            bearing = 0

            #metric conversion
            speed = str(float(speed) * 1.852)

            query_string = f"&lat={lat}&lon={lon}&speed={speed}&bearing={bearing}&timestamp={lpos}"

            dev_ids = self.filterdict.get(filter).get(boatid)
            for dev_id in dev_ids:
                query_fullstring = f"id={dev_id}" + query_string
                try:
                    self.tx_to_traccar(query_fullstring)
                except ValueError:
                    logging.warning(f"id={dev_id}")


    def tx_to_traccar(self, query: str):
        # Send position report to Traccar server
        LOGGER.debug(f"tx_to_traccar({query})")
        url = f"{self.TraccarOsmand}/?{query}"
        try:
            post = requests.post(url)
            logging.debug(f"POST {post.status_code} {post.reason} - {post.content.decode()}")
            if post.status_code == 400:
                logging.warning(
                    f"{post.status_code}: {post.reason}. Please create device with matching identifier on Traccar server.")
                raise ValueError(400)
            elif post.status_code > 299:
                logging.error(f"{post.status_code} {post.reason} - {post.content.decode()}")
        except OSError:
            logging.exception(f"Error sending to {url}")







if __name__ == '__main__':
    log_level = os.environ.get("LOG_LEVEL", "INFO")

    logging.basicConfig(level=log_level)


    def sig_handler(sig_num, frame):
        logging.debug(f"Caught signal {sig_num}: {frame}")
        logging.info("Exiting program.")
        exit(0)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    def OsmandURL(url):
        u = urlparse(url)
        u = u._replace(scheme="http", netloc=u.hostname+":5055", path = "")
        return(urlunparse(u))

    config = {}
    config["TraccarHost"] = os.environ.get("TRACCAR_HOST", DEFAULT_TRACCAR_HOST)
    config["TraccarUser"] = os.environ.get("TRACCAR_USER", "")
    config["TraccarPassword"] = os.environ.get("TRACCAR_PASSWORD", "")
    config["TraccarKeyword"] = os.environ.get("TRACCAR_KEYWORD", DEFAULT_TRACCAR_KEYWORD)
    config["TraccarInterval"] = int(os.environ.get("TRACCAR_INTERVAL", DEFAULT_TRACCAR_INTERVAL))
    config["YBInterval"] = int(os.environ.get("YB_INTERVAL", DEFAULT_YB_INTERVAL))
    config["TraccarOsmand"] = os.environ.get("TRACCAR_OSMAND", OsmandURL(config["TraccarHost"]))
    
    A2T = YB2Traccar(config)

    logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)
    sched = BlockingScheduler()
    sched.add_job(A2T.poll, 'interval', next_run_time=datetime.now(), seconds=config["TraccarInterval"])
    sched.start()



