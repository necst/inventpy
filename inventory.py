#! /usr/bin/env python

import sys
import tarfile
import glob
import argparse
import logging

#3rd party libraries
import lxml.etree

logger = logging.getLogger('inventory')

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

    def __init__(self):
        self.info = {
            'chassis_sn': None,
            'uuid': None,
            'cpu': {},
            'disks': [],
            }

    def __call__(self):
        self._parse()
        self._run()

    def _run(self):
        for f in self.args.archives:
            with tarfile.open(f, mode='r:gz') as tf:
                for ti in tf:
                    bn = os.path.basename(ti.name)
                    if bn in self.files:
                        bn = bn.replace('-', '_')
                        try:
                            getattr(self, '_parse_%s' % bn)(ti.name)
                        except Exception, e:
                            logger.warning('Not calling %s: %s', bn, e)

    def _parse_cpuinfo(self, fn):
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
        with open(fn) as f:
            for l in f:
                l = l.strip()

                if l != '':
                    key, value = l.split(':')
                    key = key.strip()

                    if key in ('vendor_id', 'cpu family', 'model', \
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
                        pass
                    i += 1
                    cpus[i] = {}

        for i, cpu in enumerate(cpus):
            pid = cpu['physical id']
            if pid not in self.info['cpu'].keys():
                self.info['cpu'][pid] = cpu

    def _parse_lshw_xml(self, fn):
        tree = lxml.etree.parse(fn)

    def _parse_dmidecode(self, fn):
        with open(fn) as f:
            s = f.read()

        try:
            self.info['chassis_sn'] = re.findall(
                'Chassis Information.*?Serial Number: ([^\n]+)',
                s, re.MULTILINE | re.DOTALL)[0]
        except Exception:
            logger.warning('No chassis serial number detected')

        try:
            self.info['uuid'] = re.findall(
                'System Information.*?UUID: ([^\n]+)',
                s, re.MULTILINE | re.DOTALL)[0]
        except Exception:
            logger.warning('No UUID detected')

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
