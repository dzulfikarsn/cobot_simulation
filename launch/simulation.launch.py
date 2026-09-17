from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg = FindPackageShare('cobot_simulation')
    robot_name = 'cobot'

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

    # Open Gazebo Simulation and bridge node
    # https://github.com/gazebosim/ros_gz/blob/ros2/ros_gz_sim/launch/ros_gz_sim.launch.py
    ros_gz_sim_launch_description = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'), 'launch', 'ros_gz_sim.launch.py'
            ])
        ]),
        launch_arguments={
            # server
            'world_sdf_file': PathJoinSubstitution([pkg, 'worlds', 'world.sdf']),
            'use_composition': 'True',
            'create_own_container': 'True',
            'container_name': 'ros_gz_container',
            # bridge
            'config_file': PathJoinSubstitution([pkg, 'config', 'cobot.bridge.yaml']),
            'bridge_name': 'cobot_bridge',
        }.items()
    )

    # spawn robot in Gazebo from '/robot_description' topic
    # https://github.com/gazebosim/ros_gz/blob/ros2/ros_gz_sim/launch/gz_spawn_model.launch.py
    gz_spawn_model_launch_description = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ros_gz_sim'), 'launch', 'gz_spawn_model.launch.py'
            ])
        ]),
        launch_arguments={
            'world': 'krsri',
            'topic': 'robot_description',
            'entity_name': robot_name,
            'allow_renaming': 'False',
            'x': '0.0',
            'y': '0.0',
            'z': '0.0',
            'R': '0.0',
            'P': '0.0',
            'Y': '0.0',
        }.items()
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
        gz_spawn_model_launch_description,
        ros_gz_sim_launch_description,
        delayed_gz_gui,
        # rviz2_launch
    ]

    return LaunchDescription(argument_list + process_list)
