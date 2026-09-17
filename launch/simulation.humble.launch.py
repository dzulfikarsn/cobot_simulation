from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

# Versi launch file ini khusus untuk ROS 2 Humble di Ubuntu 22.04.
#
# Paket 'ros_gz' di branch 'humble' tidak memiliki 'ros_gz_sim.launch.py' maupun
# 'gz_spawn_model.launch.py' (baru ada mulai branch yang lebih baru / 'ros2').
# Satu-satunya launch file yang tersedia di 'ros_gz_sim' pada Humble adalah
# 'gz_sim.launch.py', yang hanya menjalankan 'gz sim' dengan argumen 'gz_args':
# https://github.com/gazebosim/ros_gz/blob/humble/ros_gz_sim/launch/gz_sim.launch.py.in
#
# Konsekuensinya, di Humble:
# - Server + GUI Gazebo dijalankan lewat 'gz_sim.launch.py' (bukan 'ros_gz_sim.launch.py').
# - Bridge ROS<->Gazebo dijalankan manual lewat node 'parameter_bridge', karena
#   'parameter_bridge' di Humble belum mendukung parameter 'config_file' (yaml),
#   jadi daftar topic di 'config/cobot.bridge.yaml' TIDAK dipakai di sini dan harus
#   ditulis ulang sebagai argumen CLI 'topic@ros_type@gz_type' di bawah. Akibatnya,
#   'qos_profile' dan 'frame_id' yang didefinisikan di file yaml tersebut tidak akan
#   diterapkan (fitur itu hanya ada lewat 'config_file', yang tidak tersedia di Humble).
# - Robot di-spawn dengan menjalankan node 'ros_gz_sim'/'create' langsung, dengan
#   argumen command-line (gflags) bergaya '-nama nilai', karena executable 'create'
#   versi Humble hanya membaca gflags dan belum membaca ROS 2 parameters seperti
#   versi yang dipakai 'gz_spawn_model.launch.py' di branch yang lebih baru:
#   https://github.com/gazebosim/ros_gz/blob/humble/ros_gz_sim/src/create.cpp


def generate_launch_description():
    pkg = FindPackageShare('cobot_simulation')
    robot_name = 'cobot'
    world_name = 'krsri'

    # Arguments
    headless = LaunchConfiguration('headless')
    rviz2 = LaunchConfiguration('rviz2')
    use_sim_time = LaunchConfiguration('use_sim_time')
    argument_list = [
        DeclareLaunchArgument(
            'headless',
            default_value='false',
            choices=['true', 'false'],
            description='Jika diatur true, Window simulasi akan tidak ditampilkan dan simulasi tetap berjalan di latar belakang.'
        ),
        DeclareLaunchArgument(
            'rviz2',
            default_value='true',
            choices=['true', 'false'],
            description='Jika diatur true, node RViz2 akan dijalankan.'
        ),
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            choices=['true', 'false'],
            description='Jika diatur true, seluruh node yang diatur parameter use_sim_time: true akan menggunakan clock dari simulasi (/clock).'
        )
    ]

    # robot_state_publisher node
    urdf = PathJoinSubstitution([pkg, 'urdf', 'cobot.gazebo.urdf.xacro'])
    robot_description = Command(['xacro ', urdf])

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[
            {
                'robot_description': robot_description,
                'use_sim_time': use_sim_time
            }
        ]
    )

    # Jalankan Gazebo (server saja, '-s') lewat 'gz_sim.launch.py' bawaan Humble.
    # GUI dijalankan terpisah di bawah (lihat 'gz_gui') supaya bisa dimatikan lewat 'headless'.
    world_sdf_file = PathJoinSubstitution([pkg, 'worlds', 'world.sdf'])
    gz_sim_launch_description = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'), 'launch', 'gz_sim.launch.py'
            ])
        ]),
        launch_arguments={
            'gz_args': ['-r -s ', world_sdf_file],
        }.items()
    )

    # Bridge ROS <-> Gazebo, ditulis manual (menggantikan config_file: cobot.bridge.yaml)
    # karena 'parameter_bridge' di Humble belum mendukung argumen 'config_file'.
    bridge_node = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='cobot_bridge',
        output='screen',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            'sensor/camera/image@sensor_msgs/msg/Image[gz.msgs.Image',
            'sensor/range_gripper@sensor_msgs/msg/Range[gz.msgs.LaserScan',
        ],
        parameters=[{'use_sim_time': use_sim_time}],
    )

    # Spawn robot di Gazebo dari topic '/robot_description', lewat node 'create' langsung
    # (menggantikan 'gz_spawn_model.launch.py' yang tidak ada di Humble). Argumen memakai
    # gflags '-nama nilai' karena 'create' versi Humble belum membaca ROS 2 parameters.
    gz_spawn_model_node = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-world', world_name,
            '-topic', 'robot_description',
            '-name', robot_name,
            '-x', '0.0',
            '-y', '0.0',
            '-z', '0.0',
            '-R', '0.0',
            '-P', '0.0',
            '-Y', '0.0',
        ],
    )

    # show Gazebo GUI
    gui_config = PathJoinSubstitution([pkg, 'config', 'cobot.gz.view.config'])
    gz_gui = ExecuteProcess(
        cmd=['gz', 'sim', '-g', '--gui-config', gui_config],
        output='screen',
        condition=UnlessCondition(headless),
    )

    # ROS2 Controllers
    robot_controllers = PathJoinSubstitution([pkg, 'config', 'cobot.gazebo.controllers.yaml',])
    controller_spawner_node = Node(
        package='controller_manager',
        executable='spawner',
        name='controller_spawner',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            'joint_trajectory_controller',
            'gripper_controller',
            'joint_state_broadcaster',
            '--param-file', robot_controllers
        ]
    )

    delayed_gz_gui = TimerAction(
        period=7.0,
        actions=[gz_gui]
    )

    rviz2_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('cobot_bringup'), 'launch', 'rviz2.launch.py'
            ])
        ]),
        launch_arguments={
            'display_config': 'cobot.rviz',
            'use_sim_time': use_sim_time
        }.items(),
        condition=IfCondition(rviz2)
    )

    # Process List
    process_list = [
        robot_state_publisher_node,
        controller_spawner_node,
        gz_spawn_model_node,
        bridge_node,
        gz_sim_launch_description,
        delayed_gz_gui,
        # rviz2_launch
    ]

    return LaunchDescription(argument_list + process_list)
