# クライアント側
import socket
from contextlib import closing
import cv2
import numpy as np

def find_largest_redzone_rect(image,bboxsize=50):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV_FULL)
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    mask = np.zeros(h.shape, dtype=np.uint8)
    mask[((h < 15) | (h > 200)) & (s > 128)] = 255
    # Get boundary
    _, contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    
    for contour in contours:
        approx = cv2.convexHull(contour)
        rect = cv2.boundingRect(approx)
        rects.append(np.array(rect))
    largest = max(rects, key=(lambda x: x[2] * x[3])) #return maximum rectangle
    centerx = largest[0]+largest[2]/2 
    centery = largest[1]+largest[3]/2
    bbox = (centerx-bboxsize/2,centery-bboxsize/2,bboxsize,bboxsize)
    return bbox, largest

def drawrect(frame,bbox,color=(0,255,0)):
    p1 = (int(bbox[0]), int(bbox[1]))
    p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
    cv2.rectangle(frame, p1, p2, color, 2, 1)
    return frame

# video
chnum = 2
cap = cv2.VideoCapture(chnum)
print("Now channel is:",chnum)


# test capture
ret, frame = cap.read()
if not ret:
    exit(0)
wid, hei, _= frame.shape
# image center : target
cx, cy = wid/2, hei/2

# Communication
host = "192.168.100.111"
port = 8888
buf_size = 4096

#sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


# for loop
while(True):
    # Capture frame-by-frame
    ret, frame = cap.read()

    if not ret:
        print("No video input!")

    # tracker
    bbox, largest = find_largest_redzone_rect(frame)
    frame_withbb = drawrect(frame,bbox)

    # Show Track result
    cv2.imshow('tracked frame', frame_withbb)
    print(bbox,flush=True)

    # Create Data
    # u: yaw, v: -Pitch 
    data = [bbox[0] - cx, cy - bbox[1]]
    msg = str(bbox[0] - cx) + "," + str(cy - bbox[1])
    
    # send to server
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with closing(sock):
        sock.connect((host, port))
        sock.send(msg.encode())
        rmsg = sock.recv(buf_size)  #use global
        print(rmsg)

    Key = cv2.waitKey(1)
    if Key & 0xFF == ord('q'):
        break

# When everything done, release the capture
cap.release()
cv2.destroyAllWindows()