#!/usr/bin/env python3

import rospy
import rospkg
import cv2
import numpy as np
import os

from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError
from PIL import Image as imgPil
from facerecModule import *
from holisticDetectorModule import *
from PIL import ImageDraw
from scipy.spatial import ConvexHull
from perception_tests.msg import MediapipePointInfo, MediapipePointInfoArray



class MediapipeHolistic:
    def __init__(self):
        # Create the node
        node_name = "mediapipe_holistic"
        rospy.init_node(node_name, anonymous=False)
        rospy.loginfo("%s node created" % node_name)

        rospack = rospkg.RosPack()

        # Variable Initialization
        self.directory = rospack.get_path('perception_tests') + '/images/'
        self.rate = rospy.Rate(10)
        self.img = None
        self.ctr = True
        self.detector = holisticDetector()

        self.drawPose = True
        self.drawFace = False
        self.drawRightHand = False
        self.drawLeftHand = False
        self.getFaceBoundary = False
        
        self.currentEvent = None
        
        self.bridge = CvBridge()

        # Subscribe to Camera Topic
        self.image_sub = rospy.Subscriber("/camera/color/image_raw", Image, self.imgCallback)

        # Subscribe to Event and perform accordingly
        self.event_sub = rospy.Subscriber("/mediapipe_holistic/event_in", String, self.eventCallback)

        # Publish Face Landmarks
        self.mp_faceLandmarks_pub = rospy.Publisher("/mediapipe_holistic/face_landmarks", MediapipePointInfoArray, queue_size=10)
        
        # Publish Pose World Landmarks
        self.mp_poseWorldLandmarks_pub = rospy.Publisher("/mediapipe_holistic/pose_world_landmarks", MediapipePointInfoArray, queue_size=10)
        
        # Publish Img Pose Landmarks
        self.mp_imgPoseLandmarks_pub = rospy.Publisher("/mediapipe_holistic/img_pose_landmarks", MediapipePointInfoArray, queue_size=10)

        # EXTRAS
        # Publish Right Arm Length
        self.mp_rightArmLength_pub = rospy.Publisher("/mediapipe_holistic/right_arm_length", Float32, queue_size=10)
        
        # Publish Left Arm Length
        self.mp_leftArmLength_pub = rospy.Publisher("/mediapipe_holistic/left_arm_length", Float32, queue_size=10)
        
        # Publish Shoulder Length
        self.mp_shoulderLength_pub = rospy.Publisher("/mediapipe_holistic/shoulder_length", Float32, queue_size=10)

        # Publish Hip Length
        self.mp_hipLength_pub = rospy.Publisher("/mediapipe_holistic/hip_length", Float32, queue_size=10)

        # Publish Torso Length
        self.mp_torsoLength_pub = rospy.Publisher("/mediapipe_holistic/torso_length", Float32, queue_size=10)

    def run(self):
        while not rospy.is_shutdown():
            if self.currentEvent is not None:
                if self.currentEvent == "stop":
                    self.currentEvent = None
                    self.img = None
                    self.image_sub.unregister()
                    cv2.destroyAllWindows()
                    rospy.logwarn("Stopping detection!")

                if self.currentEvent == "start":
                    self.currentEvent = None
                    self.image_sub = rospy.Subscriber("/camera/color/image_raw", Image, self.imgCallback)
                    rospy.logwarn("Starting detection!")

                if self.currentEvent == "reset":
                    self.img = None
                    self.ctr = True
                    self.detector = holisticDetector()
                    self.currentEvent = None
                    self.image_sub = rospy.Subscriber("/camera/color/image_raw", Image, self.imgCallback)
                    rospy.logwarn("Reseting!")

            if self.img is not None:
                if self.ctr:
                    self.img = self.detector.find(self.img, self.drawPose, self.drawFace, self.drawRightHand, self.drawLeftHand)
                    
                    isFaceLandmarks = self.detector.getFaceLandmarks(self.img)
                    if isFaceLandmarks:
                        self.publishFaceCoordinates()
                        if self.getFaceBoundary:
                            self.img = self.getFaceMask()


                    isPoseWorldLandmarks = self.detector.getPoseWorldLandmarks()
                    if isPoseWorldLandmarks:
                        self.publishPoseWorldCoordinates()


                    isImgPoseLandmarks = self.detector.getPoseImgLandmarks(self.img)
                    if isImgPoseLandmarks:
                        self.publishPoseImgCoordinates()


                    if self.detector.getRightArmLength():
                        self.mp_rightArmLength_pub.publish(self.detector.getRightArmLength())

                    
                    if self.detector.getLeftArmLength():
                        self.mp_leftArmLength_pub.publish(self.detector.getLeftArmLength())

                    
                    if self.detector.getShoulderLength():
                        self.mp_shoulderLength_pub.publish(self.detector.getShoulderLength())

                    
                    if self.detector.getHipLength():
                        self.mp_hipLength_pub.publish(self.detector.getHipLength())


                    if self.detector.getTorsoLength():
                        self.mp_torsoLength_pub.publish(self.detector.getTorsoLength())


                    self.ctr = False
                    
              
                cv2.imshow("RealSense", self.img)
                cv2.waitKey(1)                    
            
            self.rate.sleep()


        cv2.destroyAllWindows()
        rospy.loginfo('Shutting Down MediapipeHolistic Node')


    def getFaceMask(self):
        height, width, c = self.img.shape
        mask_img = imgPil.new('L', (width, height), 0)

        points = np.array(self.detector.faceCoordinates)

        hull = ConvexHull(points)
        polygon = []
        for v in hull.vertices:
            polygon.append((points[v, 0], points[v, 1]))

        ImageDraw.Draw(mask_img).polygon(polygon, outline=1, fill=1)
        mask = np.array(mask_img)
        
        color_image = cv2.bitwise_and(self.img, self.img, mask=mask)

        return color_image


    def imgCallback(self, data):
        try:
            self.img = self.bridge.imgmsg_to_cv2(data, "bgr8")
            self.ctr = True
        except CvBridgeError as e:
            print(e)


    def eventCallback(self, data):
        # rospy.logwarn("Got new event: " + str(data.data))
        self.currentEvent = data.data

    
    def publishFaceCoordinates(self):
        msgArr = []
        for p in self.detector.faceCoordinates:
            msg = MediapipePointInfo()
            msg.x = p[0]
            msg.y = p[1]
            msg.z = -1
            msg.visibility = -1
            msgArr.append(msg)

        self.mp_faceLandmarks_pub.publish(msgArr)

    
    def publishPoseWorldCoordinates(self):
        msgArr = []
        for p in self.detector.poseCoordinates:
            msg = MediapipePointInfo()
            msg.x = p.x
            msg.y = p.y
            msg.z = p.z
            msg.visibility = p.visibility
            msgArr.append(msg)

        self.mp_poseWorldLandmarks_pub.publish(msgArr)

    
    def publishPoseImgCoordinates(self):
        msgArr = []
        for p in self.detector.imgPoseCoordinates:
            msg = MediapipePointInfo()
            msg.x = p.x
            msg.y = p.y
            msg.z = -1
            msg.visibility = p.visibility
            msgArr.append(msg)

        self.mp_imgPoseLandmarks_pub.publish(msgArr)

        

# Main function
if __name__ == '__main__':
    camera = MediapipeHolistic()
    camera.run()