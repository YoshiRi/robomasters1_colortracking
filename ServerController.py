# server側
import socket
from contextlib import closing
import threading

# message to val
def get_reference(message):
    vals = message.decode().split(',')
    if not vals:
        return [0,0]
    newlist = []
    for val in vals:
        newlist.append(float(val))
    return newlist
    
# saturation
def saturation(val,vmin=-360,vmax=360):
    return min(max(val,vmin),vmax)

# Control Program
def gimbal_tracking(diff):
    # P gain
    Kp = 1.0
    # Control Duration[s]
    Duration = 0.05
    # vref
    v_yaw = - Kp * diff[0]
    v_pitch = - Kp * diff[1]
    # set speed    
    yaw_speed = saturation(int(v_yaw),300,-300)
    pitch_speed = saturation(int(v_pitch),150,-150)
    gimbal_ctrl.rotate_with_speed(yaw_speed, pitch_speed)

    # get current gimbal
    yaw_now = gimbal_ctrl.get_axis_angle(rm_define.gimbal_axis_yaw)
    pitch_now = gimbal_ctrl.get_axis_angle(rm_define.gimbal_axis_pitch)
    
    # cobtrol
    yaw_des = yaw_speed * Duration + yaw_now
    pitch_des = pitch_speed * Duration + pitch_now
    yaw_d = saturation(yaw_des,-200,200)
    pitch_d = saturation(pitch_des,-15,30)
    gimbal_ctrl.angle_ctrl(yaw_d, pitch_d)
    
    print(v_yaw,v_pitch,yaw_now,pitch_now,pitch_d,yaw_d)




# Server with auto close
def run_server():
    # parameter
    host = '192.168.100.111'
    port = 8888
    backlog = 5
    buf_size = 1024
    timeout = 20
    #init
    #sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #sock.settimeout(timeout)
    udpServSock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udpServSock.bind((host,port)) # HOST, PORTでbinding
    udpServSock.settimeout(timeout)
    
    '''
    with closing(sock):
        sock.bind((host, port))
        sock.listen(backlog)
        while True:
            clientsocket, address = sock.accept()
            with closing(clientsocket):
                while True:
                    try:
                        msg = clientsocket.recv(buf_size)
                        #print(msg)
                        #print(get_reference(msg))
                        gimbal_tracking(get_reference(msg))
                        #clientsocket.send(b"OK")
                    except:
                        print("Break")
                        break
    '''              
    while True: 
        #udp
        data, addr = udpServSock.recvfrom(buf_size) # データ受信
        print(data)
    return


def start():
    # Gimbal Lead
    #robot_ctrl.set_mode(rm_define.robot_mode_chassis_follow)
    robot_ctrl.set_mode(rm_define.robot_mode_free)    

    # Set chasis to follow Gimbal
    #chassis_ctrl.set_follow_gimbal_offset(0)# chasis にFollow
    chassis_ctrl.set_rotate_speed(180)
    gimbal_ctrl.set_rotate_speed(100)  # 後で変えるので多分無意味
    
    run_server()
    