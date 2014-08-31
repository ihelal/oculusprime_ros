#!/usr/bin/env python

"""
notes:
-make tcp socket connection with robot java
-listen for <state> moving true -- if so send ODOMETRY_START command to firmware (via telnet-java)
	-to clear drift values
	-separate thread(?)
-read odo values every n milliseconds, then update odo topic with pose/Twist
-do not update angular pose when not moving, if so will be vast gyro drift (ie., listem for <state> move stop)
	-set angular pose change at 0 when not moving
-if angle changing much more than linear move (ie., detect turn), discard encoder data
	-would be much easier if knew direction
	-would be much easier if base_controller threw up direction info to messaging, **<<DO THIS** NO!
		Just subscribe to Twist messages!
	 so wouldn't have to read via telnet at all
if odo running, pass parameter to base_controller, so THAT could send ODOMETRY_START/REPORT COMMANDS..? 
	-doesn't really matter, since this node has to read odo via telnet anyway
	
rev_1:
-firmware knows direction, discards encoder data when turning (was way too slow doing it here)
-so we don't care if turning/forward/backward -- just keep reading a bit during slow down 
-DO need way to zero angle drift if starting from stopped - firmware?

TODO: get firmware to spit out odo data ON EVERY DIRECTION CHANGE!  NO!! is recording everything just fine, 
 parent can record direction changes - just have firmware encoder recording ignore rev++ when turning?
have this read through past buffer and  accumulate all <moved> tags!
timestapping...
TODO: dometry still overshooting linear by couple cm when interrupted by turn
  -also missing timing when switching to reverse -- probably because movement commands are followed by lag
  -maybe detect direction changes with rate data? Don't use commands as indicators. THEN push movement data to 
    serial on direction change detect
  -OK forward/back direction change detect working OK, high speed little less accurate 
  (probably missing ticks) OR slippage -- accel control may help

"""

from math import radians, sin, cos
import rospy, tf
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
import socketclient


lastupdate = 0
updateinterval = 0.25
stopped = True;
pos = [0.0, 0.0, 0.0]
before = 0
now = 0

def callback(data): # event handler for cmd_vel Twist messages
	global stopped
	stopped = False
	# updateinterval = 0.25
	if data.linear.x == 0 and data.angular.z == 0:  
		stopped = True
	# elif data.linear.x == 0 and not data.angular.z == 0:
		# updateinterval = 0.1
		
		

def broadcast(s):
	global before, pos, now
	now = rospy.Time.now()
	dt = (now-before).to_sec()
	before = now

	distance = float(s[2])/1000
	delta_x = distance * cos(pos[2])
	delta_y = distance * sin(pos[2]) 
	delta_th = radians(float(s[3]))
	pos[0] += delta_x
	pos[1] += delta_y
	pos[2] += delta_th
	
	# tf
	odom_quat = tf.transformations.quaternion_from_euler(0, 0, pos[2])
	br.sendTransform((pos[0], pos[1], 0), odom_quat, now, "base_link","odom")
	# future
	# quat = tf.transformations.quaternion_from_euler(0, 0, 0)
	# br.sendTransform((-0.054, -0.02, 0.29), quat, now, "camera_depth_frame", "base_link")
	# br.sendTransform((0, 0, 0), quat, now, "odom", "map")
	
	# odom
	odom = Odometry()
	odom.header.stamp = now
	odom.header.frame_id = "odom"

	#set the position
	odom.pose.pose.position.x = pos[0]
	odom.pose.pose.position.y = pos[1]
	odom.pose.pose.position.z = 0.0
	odom.pose.pose.orientation.x = odom_quat[0]
	odom.pose.pose.orientation.y = odom_quat[1]
	odom.pose.pose.orientation.z = odom_quat[2]
	odom.pose.pose.orientation.w = odom_quat[3]

	#set the velocity
	odom.child_frame_id = "base_link"
	odom.twist.twist.linear.x = distance / dt
	odom.twist.twist.linear.y = 0
	odom.twist.twist.linear.z = 0
	odom.twist.twist.angular.x = 0
	odom.twist.twist.angular.y = 0
	odom.twist.twist.angular.z = delta_th / dt
	
	#publish
	odom_pub.publish(odom)


# MAIN

rospy.init_node('odom_tf', anonymous=False)
before = rospy.Time.now()
br = tf.TransformBroadcaster()
odom_pub = rospy.Publisher('odom', Odometry)
rospy.Subscriber("cmd_vel", Twist, callback)
rospy.Subscriber("turtle1/cmd_vel", Twist, callback) # TODO: testing
broadcast("* * 0 0".split())

while not rospy.is_shutdown():
	t = rospy.get_time()
	
	if t-lastupdate > updateinterval: # and not stopped:
		socketclient.sendString("odometryreport")
		s = socketclient.waitForReplySearch("<state> distanceangle ")
		broadcast(s.split())
		lastupdate = now.to_sec()

	else:			
		s = socketclient.replyBufferSearch("<state> distanceangle ")
		if not s=="":
			broadcast(s.split())
			lastupdate = now.to_sec()

# shutdown

