## Video Capture
# press p/m to increase/decrease channel number
# press q to finish

import numpy as np
import cv2

print("Usage: Press q to finish, Press p/m to switch video source channel")


chnum = 0
cap = cv2.VideoCapture(chnum)
print("Now channel is:",chnum)

def change_video_ch(n):
    global chnum, cap
    chnum = n
    cap = cv2.VideoCapture(chnum)
    print("Now channel is:",chnum)


while(True):
    # Capture frame-by-frame
    ret, frame = cap.read()

    if not ret:
        if chnum == 0:
            print("No video input!")
            exit(0)
        else:
            print("No video devices in ch:", chnum," set chnum as 0.")
            change_video_ch(0)

    # Our operations on the frame come here
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Display the resulting frame
    cv2.imshow('frame', gray)
    Key = cv2.waitKey(1)
    if Key & 0xFF == ord('q'):
        break
    elif Key == ord('p'):  # ahead
        change_video_ch(chnum + 1)
    elif Key == ord('m'):
        change_video_ch(chnum - 1)
        

# When everything done, release the capture
cap.release()
cv2.destroyAllWindows()

