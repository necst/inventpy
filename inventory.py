#! /usr/bin/env python

import re
import os
import sys
import glob
import pprint
import tarfile
import argparse
import logging
import lxml.etree
import simplejson

from IPython import embed

logging.basicConfig(level=logging.DEBUG)

class Inventory(object):
    files = [
        'smart_data',
        'sensors',
        'meminfo',
        'lsusb',
        'lspci',
        'lsmod',
        'lshw-xml',
        'lshw-txt',
        'lsblk',
        'ipmitool_sensor',
        'ipmitool_sel',
        'ipmitool_sdr',
        'ipmitool_mc_info',
        'ipmitool_fru',
        'ipmitool_chassis_status',
        'ip_link',
        'dmidecode',
        'dmesg',
        'cpuinfo',]

    info_tmpl = {
        'chassis_sn': None,
        'uuid': None,
        'cpu': {},
        'disks': [],
        'hw': {}
        }

    summ_tmpl = {
        'chassis_sn': None,
        'vendor': None,
        'product': None,
        'uuid': None,
        'total_ram': 0,
        'ram_slots': 0,
        'ram_empty_slots': 0,
        'nics': 0,
        'disks': 0,
        'cpus': 0
        }

    def __init__(self):
        self.current = None
        self.info = {}
        self.summary = {}
        self.summary_txt = ''

    def __call__(self):
        self._parse()
        self._run()
        self._txt_summary()
        self._print_summary()
        self._print()

    def sizeof_fmt(self, num):
        for x in ['bytes','KB','MB','GB']:
            if num < 1024.0 and num > -1024.0:
                return "%3.1f%s" % (num, x)
            num /= 1024.0
        return "%3.1f%s" % (num, 'TB')

    def _print_summary(self):
        print self.summary_txt

    def _txt_summary(self):
        self.summary_txt = \
            '# "file", %s\n' % ', '.join(self.summ_tmpl.keys())

        for f, row in self.summary.iteritems():
            self.summary_txt += \
                '"%s", %s\n' % (f, ', '.join('"%s"' % g for g in row.values()))


    def _print(self):
        pprint.pprint(self.info)

    def _run(self):
        for f in self.args.archives:
            logging.info('Processing %s', f)
            bfn = os.path.basename(f)
            self.current = bfn
            with tarfile.open(f, mode='r:gz') as tf:
                for ti in tf:
                    bn = os.path.basename(ti.name)
                    if bn in self.files:
                        bn = bn.replace('-', '_')

                        self.info[self.current] = self.info_tmpl
                        m = getattr(self, '_parse_%s' % bn, None)
                        if m is not None:
                            logging.info('Parsing %s on %s',
                                         bn,
                                         self.current)
                            m(tf.extractfile(ti).read())
                        else:
                            logging.warning('Not calling %s', bn)
            self._summarize()

    def _summarize(self):
        logging.info('Summarizing %s' % self.current)
        self.summary[self.current] = {
            'chassis_sn': self.info[self.current]['chassis_sn'],
            'vendor': self.info[self.current]['hw']['vendor'],
            'product': self.info[self.current]['hw']['product'],
            'uuid': self.info[self.current]['uuid'],
            'total_ram': self.sizeof_fmt(float(self.info[self.current]['hw']['RAM total size'])),
            'ram_slots': self.info[self.current]['hw']['RAM slots'],
            'ram_empty_slots': self.info[self.current]['hw']['RAM empty'],
            'nics': self.info[self.current]['hw']['NICs'],
            'disks': 0,
            'cpus': len(self.info[self.current]['cpu']),
            }

    def _parse_cpuinfo(self, s):
        keep_flag = lambda x:x.lower() in (
            'nx',
            'hvm',
            'ept',
            'npt',
            'svm',
            'vmx',
            'vnmi',
            'sep',
            'smep',
            'smap',
            'sse4_1', 'sse4_2',
            'sse3', 'sse4',
            'ssse3')

        cpus = [{}]
        i = 0

        for l in s.split('\n'):
            l = l.strip()

            if l != '':
                key, value = l.split(':')
                key = key.strip()

                if key in (
                    'vendor_id', 'cpu family', 'model', \
                        'model name', 'stepping', 'cpu MHz',\
                        'cache size', 'physical id', 'siblings',\
                        'cpu cores', 'flags'):
                    if key == 'flags':
                        flags = filter(keep_flag, value.split(' '))
                        value = ' '.join(flags)

                    cpus[i][key] = value.strip()
            else:
                try:
                    cpus[i]['has_ht'] = int(cpus[i]['siblings']) == \
                        2*int(cpus[i]['cpu cores'])
                except Exception:
                    cpus[i]['has_ht'] = False

                i += 1
                cpus.append({})

        for i, cpu in enumerate(cpus):
            try:
                pid = cpu['physical id']
                if pid not in self.info[self.current]['cpu'].keys():
                    self.info[self.current]['cpu'][pid] = cpu
            except KeyError:
                pass

    def _parse_lshw_xml(self, s):
        req = {
            "product": "node/product/text()",
            "vendor": "node/vendor/text()",
            "serial": "node/serial/text()",
            #"version": "",
            #"UUID": '/node/configuration/setting[@id="uuid"]/@value',
            #"socket": "",
            "RAM total size":  'node//node[@id="memory"]/size/text()',
            "RAM type": 'node//node[@class="memory"]/node[contains(@id,"bank")]/description/text()',
            "RAM bank size": 'node//node[@class="memory"]/node[contains(@id,"bank")]/size/text()',
            #"USB port number": "",
            #"USB version": "",
            #"chipset": "",
            "L1 cache": 'node//node[description="L1 cache"]/size/text()',
            "L2 cache": 'node//node[description="L2 cache"]/size/text()',
            "L3 cache": 'node//node[description="L3 cache"]/size/text()',
            #"PS2 keyb": "",
            #"PS2 mouse": "",
            #"PCI slots": "",
            #"PCI expr slots": "",
            "NIC speeds": 'node//node[@class="network"][capabilities[capability[@id="ethernet"]]]/capacity/text()',
            "NIC models": 'node//node[@class="network"][capabilities[capability[@id="ethernet"]]]/product/text()'
            }

        tree = lxml.etree.fromstring(s)
        for k, expr in req.iteritems():
            vv = tree.xpath(expr)

            if isinstance(vv, list) and len(vv) == 1:
                vv = vv[0]

            self.info[self.current]['hw'][k] = vv

        self.info[self.current]['hw']['NICs'] = len(self.info[self.current]['hw']['NIC models'])
        self.info[self.current]['hw']['RAM slots'] = len(self.info[self.current]['hw']['RAM type'])
        self.info[self.current]['hw']['RAM empty'] = len(self.info[self.current]['hw']['RAM type']) - \
            len(self.info[self.current]['hw']['RAM bank size'])

    def _parse_dmidecode(self, s):
        try:
            self.info[self.current]['chassis_sn'] = re.findall(
                'Chassis Information.*?Serial Number: ([^\n]+)',
                s, re.MULTILINE | re.DOTALL)[0].strip()
        except Exception, e:
            logging.warning('No chassis serial number detected: %s', e)

        if self.info[self.current]['chassis_sn'] == '':
            self.info[self.current]['chassis_sn'] = 'Unknown'

        try:
            self.info[self.current]['uuid'] = re.findall(
                'System Information.*?UUID: ([^\n]+)',
                s, re.MULTILINE | re.DOTALL)[0].strip()
        except Exception, e:
            logging.warning('No UUID detected: %s', e)

        if self.info[self.current]['uuid'] == '':
            self.info[self.current]['uuid'] = 'Unknown'

    def _parse(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            'archives',
            type=glob.glob,
            help='Glob expression that should return a list of tgz-ipped files')
        parser.add_argument(
            '-output_file',
            '-o',
            type=argparse.FileType('w+'),
            default=sys.stdout,
            help='Path of the target CSV file (created if non existing)')
        self.args = parser.parse_args()

if __name__ == '__main__':
    sys.exit(Inventory()())
