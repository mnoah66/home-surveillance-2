# import the necessary packages
from pyimagesearch.tempimage import TempImage
from pyimagesearch2.keyclipwriter import KeyClipWriter
import dropbox
from picamera.array import PiRGBArray
from picamera import PiCamera
from twilio.rest import Client
from threading import Thread
import argparse
import warnings
import datetime
import imutils
import json
import time
import cv2
import os

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--conf", required=True,
        help="path to the JSON configuration file")
ap.add_argument("-o", "--output", required=True,
	help="path to output directory")
#ap.add_argument("-f", "--fps", type=int, default=10,
#	help="FPS of output video")
ap.add_argument("-d", "--codec", type=str, default="mp4v",
	help="codec of output video") #MJPG for an .avi, mp4v for an mp4
ap.add_argument("-b", "--buffer-size", type=int, default=32,
	help="buffer size of video clip writer")
args = vars(ap.parse_args())

kcw = KeyClipWriter(bufSize=args["buffer_size"])

# filter warnings, load the configuration and initialize the Dropbox
# client
warnings.filterwarnings("ignore")
conf = json.load(open(args["conf"]))
client = None


# initialize the camera and grab a reference to the raw camera capture
camera = PiCamera()
camera.resolution = tuple(conf["resolution"])
camera.framerate = conf["fps"]
rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))
 
# allow the camera to warmup, then initialize the average frame, last
# uploaded timestamp, and frame motion counter

dbx = dropbox.Dropbox("DROPBOX_KEY")

time.sleep(conf["camera_warmup_time"])
avg = None
lastUploaded = datetime.datetime.now()
consecFrames = 0
motionCounter = 0

import telegram
camera.capture('/home/pi/Desktop/image.jpg')
camera.stop_preview()
bot = telegram.Bot(token='TELEGRAM_API_KEY')
bot.send_message(chat_id=-MYCHAT, text="Security Camera is ON. A preview is below.")
bot.send_photo(chat_id=-MYCHAT, photo=open('/home/pi/Desktop/image.jpg', 'rb'))


# capture frames from the camera
for f in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
        # grab the raw NumPy array representing the image and initialize
        # the timestamp and occupied/unoccupied text
        frame = f.array
        orig = frame.copy()
        timestamp = datetime.datetime.now()
        text = "Unoccupied"
 
        # resize the frame, convert it to grayscale, and blur it
        frame = imutils.resize(frame, width=500)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        #orig = frame.copy()
        
        # if the average frame is None, initialize it
        if avg is None:
                
                avg = gray.copy().astype("float")
                rawCapture.truncate(0)
                continue
 
        # accumulate the weighted average between the current frame and
        # previous frames, then compute the difference between the current
        # frame and running average
        cv2.accumulateWeighted(gray, avg, 0.5)
        frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))
        # threshold the delta image, dilate the thresholded image to fill
        # in holes, then find contours on thresholded image
        thresh = cv2.threshold(frameDelta, conf["delta_thresh"], 255,
                cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        import imutils
        cnts = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cnts[0] if imutils.is_cv2() else cnts[1]
        #(cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
         
        # loop over the contours
        for c in cnts:
                # if the contour is too small, ignore it
                if cv2.contourArea(c) < conf["min_area"]:
                        continue
 
                # compute the bounding box for the contour, draw it on the frame,
                # and update the text
                (x, y, w, h) = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                text = "Occupied"
 
        # draw the text and timestamp on the frame
        ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")
        cv2.putText(frame, "Room Status: {}".format(text), (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        cv2.putText(frame, ts, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                0.35, (0, 0, 255), 1)
        updateConsecFrames = True
        # check to see if the room is occupied
        
        if text == "Occupied":
                motionCounter += 1
                if motionCounter >= conf["min_motion_frames"]:
                        import time
                        consecFrames = 0
                        #origFileName =  "Detection_" + time.strftime("%Y%m%d-%H%M%S") + ".jpg"
                        #cv2.imwrite('/home/pi/LocalDetection/' + origFileName, orig)
                        #print("Uploaded")
                        if not kcw.recording:
                                
                                timestamp = datetime.datetime.now()
                                # .avi for an avi (must have MJPG set in codec in args
                                p = "{}/{}.mp4".format(args["output"],timestamp.strftime("%Y%m%d-%H%M%S"))
                                kcw.start(p, cv2.VideoWriter_fourcc(*args["codec"]), conf["fps"])
                        motionCounter = 0

        
        if updateConsecFrames:
                consecFrames += 1#increment motion counter of frames wihtout motion

        kcw.update(frame)
        if kcw.recording and consecFrames == args["buffer_size"]:
                import time

                #Takes a picture of the frame, but at the end of all of the 'commotion'
                origFileName =  "Detection_" + time.strftime("%Y%m%d-%H%M%S") + ".jpg"
                cv2.imwrite('/home/pi/security/LocalDetection/' + origFileName, orig)
                kcw.finish()
                #Wait 5 seconds to ensure file is written 100%
                time.sleep(5)

                
                #path = "/{base_path}/{p}".format(base_path=conf["dropbox_base_path"], p=p)
                #dbx.files_upload(open(p, "rb").read(), path)


                #Use telegram to send the video to the group chat
                bot.send_video(chat_id=-MYCHAT, video=open(p, 'rb'))


        # check to see if the frames should be displayed to screen
        
        if conf["show_video"]:
                # display the security feed
                cv2.imshow("Security Feed", frame)
                key = cv2.waitKey(1) & 0xFF
 
                # if the `q` key is pressed, break from the lop
                if key == ord("q"):
                        break
 
        
            
        # clear the stream in preparation for the next frame
        
        rawCapture.truncate(0)


