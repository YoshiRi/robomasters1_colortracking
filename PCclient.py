# クライアント側
import socket
from contextlib import closing
import cv2
import numpy as np
import threading
import time

def find_largest_redzone_rect(image,bboxsize=50):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV_FULL)
    h = hsv[:, :, 0]
    s = hsv[:, :, 1]
    mask = np.zeros(h.shape, dtype=np.uint8)
    mask[((h < 10) | (h > 220)) & (s > 128)] = 255
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


class ClientThread(threading.Thread):
    def __init__(self, PORT=8888,HOST="192.168.100.111"):
        threading.Thread.__init__(self)
        self.kill_flag = False
        # line information
        self.HOST = HOST
        self.PORT = PORT
        self.BUFSIZE = 1024
        self.ADDR = (HOST, self.PORT)
        # tcp/udp
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def run(self):
        while True:
            try:
                global msg                
                # tcp
                #self.sock.connect(self.ADDR)
                #self.sock.send(msg.encode())
                # udp
                self.udpsock.sendto(msg.encode(), self.ADDR)
                time.sleep(0.001)
                print("send")
                # udp recv
                data, addr = self.udpsock.recvfrom(self.BUFSIZE)
                print(data)
            except:
                pass
                self.udpsock.close()
                print("close")
                self.udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                #exit()
# video
chnum = 2
cap = cv2.VideoCapture(chnum)
print("Now channel is:",chnum)


# test capture
ret, frame = cap.read()
if not ret:
    exit(0)
hei, wid, _= frame.shape
# image center : target
cx, cy = wid/2, hei/2

# Communication
host = "192.168.100.111"
port = 8888
buf_size = 1024

msg = "0,0"

th = ClientThread(PORT=port,HOST=host)
th.setDaemon(True)
th.start()

# for loop
while(True):
    # Capture frame-by-frame
    ret, frame = cap.read()

    if not ret:
        print("No video input!")

    # tracker
    try:
        bbox, largest = find_largest_redzone_rect(frame)
    except:
        exit()
    frame_withbb = drawrect(frame,bbox)

    # Show Track result
    cv2.imshow('tracked frame', frame_withbb)
    #print(bbox,flush=True)

    # Create Data
    # u: yaw, v: -Pitch 
    x = bbox[0] + bbox[2]/2
    y = bbox[1] + bbox[3]/2
    data = [cx -  x, - cy + y]
    msg = str(cx - x) + "," + str(- cy + y)
    print(data)

    Key = cv2.waitKey(1)
    if Key & 0xFF == ord('q'):
        break

# When everything done, release the capture
cap.release()
cv2.destroyAllWindows()