from multiprocessing import Process, Queue
from random import randint
from pprint import pprint
import time
import random
import json
import datetime

import gps
import requests
import smbus


###############################################
#
#	Constant
#

device_id = 1234

#	amr server
url = 'http://183.90.171.55:8080/log'

#	local
#url = 'http://localhost:8080/log'
#url = 'http://192.168.1.131:8080/log'
#url = 'http://192.168.43.155:8080/log'

#imu_offset = [ 56, -142, -294, -246, 192, 144 ]


###############################################
#
#	Global
#

# Power management registers
power_mgmt_1 = 0x6b
power_mgmt_2 = 0x6c

bus = smbus.SMBus(1) # for Revision 2 boards

# This is the address value read via the i2cdetect command
address = 0x68

# Now wake the 6050 up as it starts in sleep mode
bus.write_byte_data(address, power_mgmt_1, 0)


#################################################
#
#	Function
#
def read_byte(adr):
	return bus.read_byte_data(address, adr)

def read_word(adr):
	high = bus.read_byte_data(address, adr)
	low = bus.read_byte_data(address, adr+1)
	val = (high << 8) + low
	return val

def read_word_2c(adr):
	val = read_word(adr)
	if (val >= 0x8000):
		return -((65535 - val) + 1)
	else:
		return val

def queue_get_all(q):
	items = []
	maxItemsToRetreive = 10
	for numOfItemsRetrieved in range(0, maxItemsToRetreive):
		try:
			if numOfItemsRetrieved == maxItemsToRetreive:
				break
			items.append(q.get_nowait())
		except:
			break
	return items

###############################################
#
#	Class
#

class ImuRaw():
	'''
	Read raw data
	'''

	def __init__( self, withOffset=False ):

		if withOffset:
			#	acceleration
			self.ax = read_word_2c(0x3b) - imu_offset[0]
			self.ay = read_word_2c(0x3d) - imu_offset[1]
			self.az = read_word_2c(0x3f) - imu_offset[2]
			#	gyro
			self.gx = read_word_2c(0x43) - imu_offset[3]
			self.gy = read_word_2c(0x45) - imu_offset[4]
			self.gz = read_word_2c(0x47) - imu_offset[5]

		else:
			#	acceleration
			self.ax = read_word_2c(0x3b)
			self.ay = read_word_2c(0x3d)
			self.az = read_word_2c(0x3f)
			#	gyro
			self.gx = read_word_2c(0x43)
			self.gy = read_word_2c(0x45)
			self.gz = read_word_2c(0x47)

#		self.ax = randint( 0, 16384 )
#		self.ay = randint( 0, 16384 )
#		self.az = randint( 0, 16384 )
#		self.gx = randint( 0, 16384 )
#		self.gy = randint( 0, 16384 )
#		self.gz = randint( 0, 16384 )


###############################################
#
#	Process
#

def gps_logger( gps_data, results ):

	session = gps.gps("localhost", "2947")
	session.stream(gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)

	time.sleep(1)

	while True:

		try:
			report = session.next()
			# Wait for a 'TPV' report and get the information

			if report['class'] == 'TPV':

				if hasattr(report, 'time'):
					timestamp = report.time
				if hasattr(report, 'lat'):
					latitude = report.lat
				if hasattr(report, 'lon'):
					longitude = report.lon

				#	hack timestamp,
				#	from '2015-03-30T16:09:29.000Z' to '2015-03-30T16:09:29'
				gps_data.put( [ device_id, timestamp[0:19], latitude, longitude ] )
		except:
			print 'unable to get GPS data'

def do_post( payload, results ):
	while True:
		time.sleep(0.1)
		if not payload.empty():

			data_payload = payload.get()
#			print
#			pprint( data_payload )
			try:
				headers = {'content-type': 'application/json'}
				r = requests.post(url, data=json.dumps(data_payload), headers=headers)
				print 'Send data success,', r.status_code
			except:
				print 'Failed to send data'


###############################################
#
#	Main
#

def main():

	results = Queue()

	gps_data = Queue()
	gps_process = Process( target=gps_logger, args=( gps_data, results ) )

	payload = Queue()
	post_process = Process( target=do_post, args=( payload, results ) )


	##########################################
	#
	#	Initialize
	#


	if not gps_data.empty():
		data_list = gps_data.get()
	else:
		data_list = [ device_id, False, False, False ]
		#data_list = [ device_id, '2015-03-30T16:09:29', 100.123123, 35.232323 ]

	imu = ImuRaw()
	lastReadTime = time.time()
	lastPostTime = time.time()

	gps_process.start()
	post_process.start()

	imu_list = list()
	while True:

		if time.time() - lastPostTime >= 2:
#		if not gps_data.empty():

			#	pack and send data
			data_list.append( imu_list )
			print '------------------------'
			print 'Sending data...'
			print data_list[:4], '[', data_list[4][0], ', ... ]'
			payload.put( data_list )

			#	Reset
			imu_list = list()
			lastPostTime = time.time()

			if not gps_data.empty():
				all_gps = queue_get_all( gps_data )
				data_list = all_gps[-1]
			else:
				#	add new dummy gps data
				data_list = [ device_id, False, False, False ]
				#data_list = [ device_id, '2015-03-30T16:09:29', 100.123123, 35.232323 ]


		#########################
		#	read imu data

		try:
			imu = ImuRaw()
		except:
			continue

		#	time period
		now = time.time()
		dt = now - lastReadTime
		lastReadTime = now

		imu_list.append( [
			imu.ax,
			imu.ay,
			imu.az,
			imu.gx,
			imu.gy,
			imu.gz,
			dt
		] )


if __name__ == '__main__':
	main()
