# set mode for control
## 1:robot_mode_chassis_follow: Gimbal Lead
## 2:robot_mode_gimbal_follow: Chasis Lead
## 3:robot_mode_free: Motion Isolated
robot_ctrl.set_mode(rm_define.robot_mode_free)

# yaw positive is right side
gimbal_ctrl.set_rotate_speed(100)
gimbal_ctrl.yaw_ctrl(10)
gimbal_ctrl.yaw_ctrl(-10)
gimbal_ctrl.yaw_ctrl(0)

# pitch positive is upper side
gimbal_ctrl.pitch_ctrl(10)
gimbal_ctrl.pitch_ctrl(-10)
gimbal_ctrl.pitch_ctrl(20)


# Gimbal Lead
robot_ctrl.set_mode(rm_define.robot_mode_chassis_follow)

# Set chasis to follow Gimbal
chassis_ctrl.set_follow_gimbal_offset(0)
chassis_ctrl.set_rotate_speed(180)

# yaw positive is right side
gimbal_ctrl.set_rotate_speed(100)
gimbal_ctrl.yaw_ctrl(60)
gimbal_ctrl.yaw_ctrl(-60)
gimbal_ctrl.yaw_ctrl(0)

# Not working During Chasis Follow Control
chassis_ctrl.rotate_with_degree(rm_define.clockwise,30)
chassis_ctrl.rotate_with_degree(rm_define.anticlockwise,30)


# Back to Origin Angle After Program