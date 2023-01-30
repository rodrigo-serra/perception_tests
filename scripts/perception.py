#!/usr/bin/env python3

import rospy
import cv2
import numpy as np
import signal
import math

from std_msgs.msg import String, Float32
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge, CvBridgeError
from darknet_ros_py.msg import RecognizedObjectArrayStamped
from sympy import Point, Polygon, Line

# from mbot_perception_msgs.msg import TrackedObject3DList, TrackedObject3D, RecognizedObject3DList, RecognizedObject3D
# from mbot_perception_msgs.srv import DeleteObject3D, DeleteObject3DRequest

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class Perception():
    __metaclass__ = Singleton
    def __init__(self, useYolo, easyDetection, useFilteredObjects, classNameToBeDetected):
        # self.tracked_objects=None
        # self.subscriber = rospy.Subscriber("/bayes_objects_tracker/tracked_objects", TrackedObject3DList, self.__trackCallback)

        # Variable Initialization
        self.img = None
        self.readObj = False
        self.pointingDirection = None
        self.pointingSlope = None
        self.pointingIntercept = None
        self.bridge = CvBridge()

        # Handle CTRL-C Interruption
        signal.signal(signal.SIGINT, self.handler)
        
        #
        self.useYolo = useYolo
        self.easyDetection = easyDetection
        self.useFilteredObjects = useFilteredObjects
        self.classNameToBeDetected = classNameToBeDetected

        # Variables
        self.detectedObjects = []
        self.filteredObjects = []

        # Msgs are defined in the mediapipeHolisticnode
        self.pointingLeftMsg = "left"
        self.pointingRightMsg = "right"

        # Topics
        if self.useYolo == True:
            self.camera_topic = "/object_detector/detection_image/compressed"
            self.readImgCompressed = True
            self.detectedObjects_topic = "/object_detector/detections"
        else:
            self.camera_topic = "/camera/color/image_raw"
            self.readImgCompressed = False
            self.detectedObjects_topic = "/detectron2_ros/result_yolo_msg"


        self.pointingDirection_topic = "/perception/mediapipe_holistic/hand_pointing_direction"
        self.pointingSlope_topic = "/perception/mediapipe_holistic/hand_pointing_slope"
        self.pointingIntercept_topic = "/perception/mediapipe_holistic/hand_pointing_intercept"


        # Subscribe to Camera Topic
        if self.readImgCompressed:
            self.image_sub = rospy.Subscriber(self.camera_topic, CompressedImage, self.imgCallback)
        else:
            self.image_sub = rospy.Subscriber(self.camera_topic, Image, self.imgCallback)

        
        self.objDetection_sub = rospy.Subscriber(self.detectedObjects_topic, RecognizedObjectArrayStamped, self.readDetectedObjects)

        self.pointingDirection_sub = rospy.Subscriber(self.pointingDirection_topic, String, self.getPointingDirection)

        self.pointingSlope_sub = rospy.Subscriber(self.pointingSlope_topic, Float32, self.getPointingSlope)

        self.pointingIntercept_sub = rospy.Subscriber(self.pointingIntercept_topic, Float32, self.getPointingIntercept)

    

    def run(self):
        while(not self.readObj):
            rospy.loginfo("Waiting for Object Detection...")

        if self.detectedObjects == []:
            rospy.loginfo("No objects were detected!")

        if self.easyDetection:
            while(self.pointingDirection is None):
                rospy.loginfo("Getting pointing direction...")

            return  self.findObjectSimplifiedVersion()
        
        else:
            while(self.img is None):
                rospy.loginfo("Getting img...")

            while(self.pointingSlope is None and self.pointingIntercept is None):
                rospy.loginfo("Getting pointing slope and intercept...")

            res = self.lineIntersectionPolygon()
            if res != None:
                return res
            else:
                return self.findClosestObjectToLine()



    def imgCallback(self, data):
        try:
            if self.readImgCompressed:
                self.img = self.bridge.compressed_imgmsg_to_cv2(data, "bgr8")
            else:
                self.img = self.bridge.imgmsg_to_cv2(data, "bgr8")


        except CvBridgeError as e:
            print(e)


    def getPointingDirection(self, data):
        self.pointingDirection = data.data

    
    def getPointingSlope(self, data):
        self.pointingSlope = data.data

    
    def getPointingIntercept(self, data):
        self.pointingIntercept = data.data


    def readDetectedObjects(self, data):
        if self.useFilteredObjects:
            for obj in data.objects.objects:
                if obj.class_name == self.classNameToBeDetected:
                    self.detectedObjects.append(obj)
        else:
            for obj in data.objects.objects:    
                self.detectedObjects.append(obj)

        self.readObj = True

    
    def findObjectSimplifiedVersion(self):
        if self.pointingDirection != None:
            if self.pointingDirection == self.pointingLeftMsg:
                for idx, obj in enumerate(self.detectedObjects):
                    if idx == 0:
                        left_obj = obj

                    if obj.bounding_box.x_offset > left_obj.bounding_box.x_offset:
                        left_obj = obj

                return left_obj

            
            if self.pointingDirection == self.pointingRightMsg:
                for idx, obj in enumerate(self.detectedObjects):
                    if idx == 0:
                        right_obj = obj

                    if obj.bounding_box.x_offset < right_obj.bounding_box.x_offset:
                        right_obj = obj

                return right_obj

        return None


    def lineIntersectionPolygon(self):
        if self.pointingSlope != None and self.pointingIntercept != None:
            h, w, c = self.img.shape
            x1, x2 = 0, w
            y1, y2 = self.pointingIntercept * x1 + self.pointingIntercept, self.pointingSlope * x2 + self.pointingIntercept
            line = Line(Point(x1, y1), Point(x2, y2))
            for obj in self.detectedObjects:
                x_top_left = obj.bounding_box.x_offset
                y_top_left = obj.bounding_box.y_offset

                x_bottom_left = obj.bounding_box.x_offset
                y_bottom_left = obj.bounding_box.y_offset + obj.bounding_box.height

                x_top_right = obj.bounding_box.x_offset + obj.bounding_box.width
                y_top_right = obj.bounding_box.y_offset

                x_bottom_right = obj.bounding_box.x_offset + obj.bounding_box.width
                y_bottom_right = obj.bounding_box.y_offset + obj.bounding_box.height
        
                p1, p2, p3, p4, p5 = map(Point, [(x_bottom_left, y_bottom_left), (x_bottom_right, y_bottom_right), (x_top_right, y_top_right), (x_top_left, y_top_left), (x_bottom_left, y_bottom_left)])
                
                poly = Polygon(p1, p2, p3, p4, p5)

                isIntersection = poly.intersection(line)

                if isIntersection != []:
                    return obj

        return None


    def findClosestObjectToLine(self):
        returnObject = None
        returnDist = None
        
        if self.pointingSlope != None and self.pointingIntercept != None:
            perpendicularLineSlope = -1 / self.pointingSlope

            for idx, obj in enumerate(self.detectedObjects):
                # Find Bounding Box Center
                obj_boundingBoxCenter_x = obj.bounding_box.x_offset + obj.bounding_box.width / 2
                obj_boundingBoxCenter_y = obj.bounding_box.y_offset + obj.bounding_box.height / 2

                # Find Intercept of the perpendicular line
                perpendicularLineIntercept = obj_boundingBoxCenter_y - perpendicularLineSlope * obj_boundingBoxCenter_x

                # Find Intersection (Point)
                inter_x = (perpendicularLineIntercept - self.pointingIntercept) / (self.pointingSlope - perpendicularLineSlope)
                inter_y = self.pointingSlope * inter_x + self.pointingIntercept

                # Compute Distance between those two points (intersection and bounding box center)
                dx = math.pow(obj_boundingBoxCenter_x - inter_x, 2)
                dy = math.pow(obj_boundingBoxCenter_y - inter_y, 2)
                dist = math.sqrt(dx + dy)
                
                if idx == 0:
                    returnObject = obj
                    returnDist = dist
                
                if idx > 0 and returnDist > dist:
                    returnObject = obj
                    returnDist = dist

        return returnObject


    def handler(self, signum, frame):
        exit(1)
    

    # def __trackCallback(self,data):
    #     self.tracked_objects = data



    # def get_objects_tracker(self, confidence):
    #     # get object message
    #     tracked_objects = rospy.wait_for_message("/bayes_objects_tracker/tracked_objects", TrackedObject3DList)
    #     object_frame = tracked_objects.header.frame_id
    #     tracked_objects = tracked_objects.objects

    #     object_dict = dict()
    #     for object in tracked_objects:
    #         obj_index = np.argmax(object.class_probability)

    #         if object.class_probability[obj_index] > confidence:
    #             new_object_name = object.class_name[obj_index]
    #             new_object_info = [object.uuid, object.class_probability[obj_index],
    #                             object.pose.pose.position.x, object.pose.pose.position.y, object.pose.pose.position.z,
    #                             object.pose.pose.orientation.x, object.pose.pose.orientation.x, object.pose.pose.orientation.x,
    #                             object.pose.pose.orientation.w]

    #             # check if object already exists and remove it
    #             repeated_obj_uuid, pruned_dict = self.__check_object_repetition(new_object_name, new_object_info, object_dict, obj_min_distance=0.2, remove_obj=True)
    #             if repeated_obj_uuid:
    #                 object_dict = pruned_dict

    #             # add new perceived object
    #             if new_object_name in object_dict.keys():
    #                 object_dict[new_object_name].append(new_object_info)
    #             else:
    #                 object_dict[new_object_name] = [new_object_info]

    #     return object_dict, object_frame

    # def __check_object_repetition(self, new_object_name, new_object_info, dict_objects, obj_min_distance=0.2, remove_obj=True):
    #     if remove_obj:
    #         pruned_dict = dict_objects.copy()
    #     new_obj_uuid = new_object_info[0]
    #     new_obj_pos = [new_object_info[2], new_object_info[3], new_object_info[4]]

    #     for obj_name, obj_info_list in dict_objects.items():
    #         for obj_index, obj_info in enumerate(obj_info_list):
    #             obj_uuid = obj_info[0]
    #             obj_pos = [obj_info[2], obj_info[3], obj_info[4]]
    #             if obj_uuid == new_obj_uuid or self.__euclidean_distance(new_obj_pos, obj_pos) < obj_min_distance:
    #                 if remove_obj:
    #                     del pruned_dict[obj_name][obj_index]
    #                     if not pruned_dict[obj_name]:
    #                         del pruned_dict[obj_name]

    #                     return obj_uuid, pruned_dict
    #                 else:
    #                     return obj_uuid, None

    #     return None, None

    # def __euclidean_distance(self, p1, p2):
    #     return np.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)

    # def start_tracker(self):
    # 	rospy.loginfo("Initializing object tracker...")
    # 	object_tracker_init = rospy.Publisher('/bayes_objects_tracker/event_in', String, queue_size=1)
    # 	rospy.sleep(0.5)
    # 	object_tracker_init.publish('e_start')

    # def stop_tracker(self):
    #     rospy.loginfo("Stopping object tracker...")
    #     object_tracker_init = rospy.Publisher('/bayes_objects_tracker/event_in', String, queue_size=1)
    #     rospy.sleep(0.5)
    #     object_tracker_init.publish('e_stop')

    # def delete_tracked_objects(self):
    #     self.start_tracker()
    #     rospy.sleep(0.1)
    #     tracked_objects = rospy.wait_for_message("/bayes_objects_tracker/tracked_objects", TrackedObject3DList)
    #     object_frame = tracked_objects.header.frame_id
    #     tracked_objects = tracked_objects.objects

    #     self.stop_tracker()
    #     clear_tracker_srv = rospy.ServiceProxy('/bayes_objects_tracker/delete_object', DeleteObject3D)
    #     rospy.sleep(0.1)
    #     clear_tracker_srv.wait_for_service(timeout=rospy.Duration(5))

    #     for obj in tracked_objects:
    #         delete_obj = DeleteObject3DRequest()
    #         delete_obj.uuid = obj.uuid
    #         rospy.loginfo(delete_obj)

    #         try:
    #             clear_tracker_srv.call(delete_obj)
    #         except:
    #             continue
    #         # rospy.sleep(0.1)

    #     self.start_tracker()

    # def get_number_of_objects(self, object_name, confidence=0.8):
    #     objects_dict = self.get_objects_tracker(confidence=confidence)
    #     if object_name in objects_dict.keys():
    #         return len(object_list[object_name])
    #     else:
    #         return 0

    # # TODO: implement get_objects_classes
    # def detect_object(self, class_to_detect):
    #     pass

    # # TODO: implement get_objects_classes
    # def get_objects_classes(self, perceive_time, confidence):
    #     pass

    # TODO: finish implementing get_objects_locations (check object repetition is not adapted to this message type, but the rest is done)
    # def get_objects_locations(self, perceive_time, confidence):
    #     tracked_objects = []
    #     initial_time = rospy.get_time()
    #     elapsed_time = -np.inf
    #     while perceive_time > elapsed_time:
    #         obj_msg = rospy.wait_for_message("/localized_objects", RecognizedObject3DList)
    #         object_frame = obj_msg.image_header.frame_id
    #         for obj in obj_msg.objects
    #             tracked_objects.append(obj)
    #         elapsed_time = rospy.get_time() - initial_time
    #
    #     object_dict = dict()
    #     for object in tracked_objects:
    #         if object.confidence > confidence:
    #             new_object_name = object.class_name
    #             new_object_info = [object.confidence,
    #                             object.pose.position.x, object.pose.position.y, object.pose.position.z,
    #                             object.pose.orientation.x, object.pose.pose.orientation.x, object.pose.orientation.x,
    #                             object.pose.orientation.w]
    #
    #             # check if object already exists and remove it
    #             repeated_obj_uuid, pruned_dict = self.__check_object_repetition(new_object_name, new_object_info, object_dict, obj_min_distance=0.2, remove_obj=True)
    #             if repeated_obj_uuid:
    #                 object_dict = pruned_dict
    #
    #             # add new perceived object
    #             if new_object_name in object_dict.keys():
    #                 object_dict[new_object_name].append(new_object_info)
    #             else:
    #                 object_dict[new_object_name] = [new_object_info]
    #
    #     return object_dict, object_frame


# if __name__ == '__main__':
#     rospy.init_node('perception_action', anonymous=True)
#     perception = Perception()
#     objects, object_frame = perception.get_objects_tracker(confidence=0.5)
#     print(objects)
#     print(object_frame)


def main():
    # Read Arguments
    yolo = True
    easyDetection = False
    useFilteredObjects = True
    classNameToBeDetected = "backpack"
    
    node_name = "perception_action"
    rospy.init_node(node_name, anonymous=True)
    rospy.loginfo("%s node created" % node_name)

    n_percep = Perception(yolo, easyDetection, useFilteredObjects, classNameToBeDetected)
    obj = n_percep.run()
    rospy.loginfo(obj)

    return obj


# Main function
if __name__ == '__main__':
    main()