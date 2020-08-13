# これから何しよっか


## やったこと
- 接続周り
  - 接続OK
  - メッセージ送信



## やること
- 画像処理用


# プログラム

## ジンバル

右向きがYawの正，上向きがPitchの正

gimbal_followモードが良さそう

位置制御

```python
# Gimbal Lead
robot_ctrl.set_mode(rm_define.robot_mode_chassis_follow)

# Set chasis to follow Gimbal
chassis_ctrl.set_follow_gimbal_offset(0)
chassis_ctrl.set_rotate_speed(180)
gimbal_ctrl.set_rotate_speed(100)

# yaw positive is right side
gimbal_ctrl.yaw_ctrl(60)
gimbal_ctrl.yaw_ctrl(-60)
gimbal_ctrl.yaw_ctrl(0)
```

速度制御

```python
# Gimbal Lead
robot_ctrl.set_mode(rm_define.robot_mode_chassis_follow)

# Set chasis to follow Gimbal
chassis_ctrl.set_follow_gimbal_offset(0)
chassis_ctrl.set_rotate_speed(180)
gimbal_ctrl.set_rotate_speed(100)#無意味

gimbal_ctrl.rotate_with_speed(30, 10)
# 速度のOpenループは許されなかったorz
gimbal_ctrl.angle_ctrl(60, 15)
```

## Video Capture

RobomasterのVideoをCaptureする。

- OBS Studioを管理者権限で起動。（なぜならばRobomasterのアプリが管理者権限で起動するから）
- シーンを追加，ソースから「ゲームキャプチャを追加」
- 「ツール」→「Virtual Cam」

![](img/RobomasCapture.png)

## Visual Tracking

超雑に考えると，uとvがそれぞれYaw（正）とPitch（負）に当てはまる。
ビジュアルサーボにおける速度制御が妥当と思われる。

$$
d = [u-u0,-(v-v0)]
$$

とすると，

$$
v = - K_p d
$$

とするべきだろう。$K_p$はPゲイン。速度制御は厳密にはできないので一定時刻動いてもらうことにする。


```python



```

## データ通信

サーバとクライアントの通信確認

```python
# server側
import socket
from contextlib import closing

# message to val
def get_reference(message):
    vals_= message.decode().split(',')
    newlist = []
    for val in vals:
        newlist.append(float(val))
    return newlist

def run_server():
    # parameter
    host = '127.0.0.1'
    port = 8888
    backlog = 5
    buf_size = 4096
    timeout = 60
    #init
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    with closing(sock):
        sock.bind((host, port))
        sock.listen(backlog)
        while True:
            clientsocket, address = sock.accept()
            with closing(clientsocket):
                msg = clientsocket.recv(buf_size)
                print(msg)
                print(get_reference(msg))
                clientsocket.send(msg)
    return

print("Exit!")
```

