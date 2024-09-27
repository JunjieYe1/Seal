import json
import os
import time
from threading import Thread, Lock
import webbrowser
from threading import Timer
import serial
import serial.tools.list_ports
from flask import Flask, render_template, jsonify

data_lock = Lock()

app = Flask(__name__)

# 全局变量用于存储从单片机读取的数据
data_from_serial = "等待数据中..."
recent_data_from_serial = []
file_path = "data.json"

avg_magx, avg_magy, avg_magz = 0, 0, 0
# 初始化用于存储PP平均值的全局字典
pp_averages = {"PP_1": 0, "PP_2": 0, "PP_3": 0, "PP_4": 0}
# 全局变量用于跟踪按压状态和最大按压值
is_pressing = False
max_press_value = 0
max_press_location = None
max_press_rotation = 0

seal_start_r = 0

seal_is_moved = False

sleep_count = 0
time_count = 0
current_paper = 0
start_location = 0

base_position_x, base_position_y = 3193, 3860  # 初始基准值
threshold = 400  # 偏移阈值
abnormal_positions = [base_position_x, base_position_y]  # 存储最近的异常坐标
current_xy = [0, 0]
is_pressing_pos = False
is_ending = False


def convert_keys_to_int(d):
    """尝试将字典的键从字符串转换为整数。"""
    new_dict = {}
    for k, v in d.items():
        try:
            # 尝试将键转换为整数
            new_dict[int(k)] = v
        except ValueError:
            # 如果键不能转换为整数，则保持原样
            new_dict[k] = v
    return new_dict


def load_config(filename):
    """加载配置文件，并处理字典键为整数。"""
    with open(filename, 'r', encoding='utf-8') as config_file:
        config = json.load(config_file)

    # 处理各个字典数据
    config['seal_location_dict'] = convert_keys_to_int(config['seal_location_dict'])
    config['correct_seal_dict'] = convert_keys_to_int(config['correct_seal_dict'])
    config['paper_code_to_image_url'] = convert_keys_to_int(config['paper_code_to_image_url'])
    config['seal_dict'] = convert_keys_to_int(config['seal_dict'])

    # 如果有其他需要处理的字典，可以继续添加处理逻辑
    # 示例：config['another_dict'] = convert_keys_to_int(config['another_dict'])

    return config


# 加载配置文件
config = load_config('config.json')

port_num = config['port_num']
seal_move_diff = config['seal_move_diff']
pressure_range = config['pressure_range']
seal_location_dict = config['seal_location_dict']
correct_seal_dict = config['correct_seal_dict']
paper_code_to_image_url = config['paper_code_to_image_url']
seal_dict = config['seal_dict']

seal_no = 0,

scores = {
    'seal_no': False,
    'angle': 5,
    'press': 5,
    'no_slip': 25,
    'location': 5
}


def write_data_to_file(data):
    """将数据写入文件"""
    with open(file_path, 'w') as f:
        json.dump(data, f)


def read_data_from_file():
    """从文件读取数据"""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
    return []


def reset_pos():
    global abnormal_positions
    abnormal_positions = [base_position_x, base_position_y]


def normalize(x, lower_bound=900, upper_bound=3570, middle_point=2000):
    if x <= lower_bound:
        return 0
    elif x >= upper_bound:
        return 1
    elif x <= middle_point:
        # Normalize between lower_bound and middle_point (900 to 2000)
        return (x - lower_bound) / (middle_point - lower_bound) * 0.5
    else:
        # Normalize between middle_point and upper_bound (2000 to 3570)
        return 0.5 + (x - middle_point) / (upper_bound - middle_point) * 0.5


def auto_detect_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        try:
            ser = serial.Serial(port.device, 9600, timeout=1)
            ser.close()
            return port.device
        except (OSError, serial.SerialException):
            continue
    return None


# 尝试打开串行端口并在后台读取数据的函数
def read_serial_data():
    global port_num
    ser = None
    buffer = ""  # 用于累积从串行端口读取的数据

    try:
        ser = serial.Serial('COM' + str(port_num), 9600, timeout=1)  # 设置超时为None以持续等待数据

    except serial.SerialException as e:
        print(f"预设串口 {port_num} 无法打开: {e}")
        # 如果预设端口号失败，尝试自动检测其他端口
        print("尝试自动检测可用的串口...")
        new_port = auto_detect_port()
        if new_port:
            port_num = new_port  # 更新全局变量 port_num
            print(f"检测到可用的串口: {port_num}")
            try:
                ser = serial.Serial(port_num, 9600, timeout=1)
            except serial.SerialException as e:
                print(f"自动检测的串口 {port_num} 无法打开: {e}")
                return
        else:
            print("未能找到可用的串口")
            return

    try:

        while True:
            data = ser.read(ser.in_waiting or 1).decode('iso-8859-1')  # 读取所有可用的数据
            buffer += data  # 将新数据追加到缓冲区

            start_pos = buffer.find('$')
            if start_pos != -1:
                end_pos = buffer.find('$', start_pos + 1)
                reset_pos = buffer.find('Reset')
                if end_pos == -1 and reset_pos != -1:
                    end_pos = reset_pos + 5
                    print(end_pos)
                if end_pos != -1:
                    segment = buffer[start_pos + 1:end_pos]
                    # print(segment)

                    with data_lock:  # 锁定列表操作
                        recent_data_from_serial.insert(0, segment)
                        if len(recent_data_from_serial) > 10:
                            recent_data_from_serial.pop()
                        write_data_to_file(recent_data_from_serial)
                    # print(recent_data_from_serial)

                    buffer = buffer[end_pos:]  # 从缓冲区删除已处理的部分
            time.sleep(0.1)

    except serial.SerialException as e:
        print(f"串口异常: {e}")
    except Exception as e:
        print(f"发生错误: {e}")
    finally:
        if ser:
            ser.close()


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/test')
def test():
    return render_template('test.html')


@app.route('/data')
def data():
    global recent_data_from_serial, base_position_x, base_position_y, abnormal_positions, current_xy, is_pressing_pos

    _data = read_data_from_file()
    recent_data_from_serial = _data

    if recent_data_from_serial:
        for entry in recent_data_from_serial:
            if 'Position_X' in entry and 'Position_Y' in entry:
                pos_x = int(entry.split('Position_X:')[1].split(';')[0])
                pos_y = int(entry.split('Position_Y:')[1].split(';')[0])
                current_xy = [pos_x, pos_y]

                # 检查是否偏移超过阈值
                if (abs(pos_x - base_position_x) + abs(pos_y - base_position_y)) > threshold:
                    abnormal_positions = [pos_x, pos_y]
                    is_pressing_pos = True
                else:
                    is_pressing_pos = False
        # print(is_pressing_pos)
        return jsonify(data=''.join(str(item) for item in recent_data_from_serial))
    else:
        return jsonify(data=data_from_serial)


def calculate_average_pp(data, x):
    # 初始化临时存储平均值的字典
    temp_averages = {}
    # 假设data是最近的数据列表，x是考虑的数据数量
    for pp_key in ["PP_1", "PP_2", "PP_3", "PP_4"]:
        pp_values = [int(entry.split(pp_key + '=')[1].split(';')[0]) for entry in data[-x:] if pp_key + '=' in entry]
        if pp_values:
            temp_averages[pp_key] = sum(pp_values) / len(pp_values)
    return temp_averages


def sleep_count_tick(sleep_count):
    if sleep_count > 0:
        return sleep_count - 1
    return 0


def calculate_diff_pp():
    global pp_averages, is_pressing, max_press_value, max_press_location, max_press_rotation, seal_start_r, \
        seal_move_diff, seal_is_moved, sleep_count, time_count, scores, abnormal_positions, start_location, is_ending
    # print(scores)
    sleep_count = sleep_count_tick(sleep_count)
    time_count = sleep_count_tick(time_count)
    new_dict = calculate_average_pp(recent_data_from_serial, 1)

    if pp_averages == {"PP_1": 0, "PP_2": 0, "PP_3": 0, "PP_4": 0}:
        return None, [50, 50], 0, scores

    current_max_diff = sum(abs(int(new_dict[key]) - int(pp_averages[key])) for key in ["PP_1", "PP_2", "PP_3", "PP_4"])
    print(current_max_diff)

    # 每次计算新的位置
    current_location = calculate_press_location()
    r = parse_seal_data()

    # print(current_rotation, scores['angle'])
    # current_rotation = current_rotation + 0.1 / 1.5


    if is_pressing and current_max_diff > max_press_value:
        max_press_value = current_max_diff
        # max_press_location = current_location  # 更新位置记录
        print(max_press_location)

        if seal_start_r != 0:
            if abs(seal_start_r - r["seal_azimuth"]["Yaw"]) > seal_move_diff:
                seal_is_moved = True

        print(seal_is_moved)

    if is_pressing:
        print(
            f"Pressing... Current Max Value: {max_press_value}, Location: {start_location}, Rotation:{max_press_rotation}")

    # 检测按压开始和结束
    if is_pressing_pos and not is_pressing and sleep_count == 0 and (r and r["status"] == '拿起'):
        print("【开始按压】")
        sleep_count = 10
        is_pressing = True
        start_location = current_location

        seal_start_r = r["seal_azimuth"]["Yaw"]
        seal_is_moved = False

        if r:
            current_rotation = r["seal_azimuth"]["Yaw"] if r else 0

            if 0 <= current_rotation <= 15 or 345 <= current_rotation <= 360:
                scores['angle'] = 25
            elif 15 <= current_rotation <= 30 or 330 <= current_rotation <= 345:
                scores['angle'] = 15
            elif 30 <= current_rotation <= 45 or 315 <= current_rotation <= 330:
                scores['angle'] = 10
            else:
                scores['angle'] = 0

            max_press_rotation = current_rotation
        # print(seal_is_moved)


    elif (not is_pressing_pos and time_count == 0) and is_pressing:
        # 按压结束，返回最大按压值时的位置和结果
        is_pressing = False
        if max_press_value in range(pressure_range[1], pressure_range[2]):
            scores['press'] = 25
        elif max_press_value in range(pressure_range[0], pressure_range[1]):
            scores['press'] = 15

        if seal_is_moved:
            scores['no_slip'] = 5
        if current_paper and current_paper in correct_seal_dict.keys() and seal_no == correct_seal_dict[current_paper]:
            scores['seal_no'] = True

        location_range = 3

        if current_paper != 0 and current_paper in seal_location_dict.keys():
            # if current_paper == 111222666:
            #     if abs(max_press_location[0] - seal_location_dict[current_paper][0]) < 1:
            #         scores['location'] = 15
            #         max_press_location[0] = seal_location_dict[current_paper][0]
            #
            #     elif abs(max_press_location[0] - seal_location_dict[current_paper][0]) < 3 and abs(
            #             max_press_location[1] - seal_location_dict[current_paper][1]) < 6:
            #
            #         scores['location'] = 25
            #         max_press_location[0] = seal_location_dict[current_paper][0]
            #         max_press_location[1] = seal_location_dict[current_paper][1]
            #
            #     else:
            #         scores['location'] = 0
            # else:
            if abs(start_location[0] - seal_location_dict[current_paper][0]) < location_range and abs(
                    start_location[1] - seal_location_dict[current_paper][1]) < location_range:
                scores['location'] = 25
                start_location[0] = seal_location_dict[current_paper][0]
                start_location[1] = seal_location_dict[current_paper][1]
            elif abs(start_location[0] - seal_location_dict[current_paper][0]) < location_range * 2 and abs(
                    start_location[1] - seal_location_dict[current_paper][1]) < location_range * 2:
                scores['location'] = 15

        result = get_press_result(max_press_value, seal_is_moved)
        print(
            f"【按压结束】 Max Value: {max_press_value}, Result: {result}, Location: {start_location}, Rotation:{max_press_rotation}")

        print(seal_is_moved)
        time_count = 50
        seal_is_moved = False
        max_press_value = 0  # 重置最大按压值
        last_location = start_location  # 一开始的位置
        last_rotation = max_press_rotation
        max_press_rotation = 0
        print(last_location)
        reset_pos()

        return result, last_location, last_rotation, scores

    return None, [50, 50], 0, scores


def get_press_result(press_value, seal_is_moved):
    global seal_no, seal_dict
    if press_value < pressure_range[1]:
        return seal_dict[seal_no]["浅"]
    elif press_value < pressure_range[2]:
        if seal_is_moved:
            return seal_dict[seal_no]["移"]
        else:
            return seal_dict[seal_no]["正"]
    else:
        return seal_dict[seal_no]["深"]


def calculate_press_location():
    global abnormal_positions
    # 每个角的位置坐标（屏幕坐标系，原点在左上角）
    positions = {
        "PP_1": (32, 98),  # 左下角
        "PP_2": (68, 98),  # 右下角
        "PP_3": (68, 2),  # 右上角
        "PP_4": (32, 2)  # 左上角
    }

    position_y, position_x = abnormal_positions  # 颠倒xy
    # print(f"Device coordinates: ({position_x}, {position_y})")

    # 将 position_x 和 position_y 归一化到 0-1 之间
    max_value_x = 3500  # 假设 position_x 的最大值为 4000
    max_value_y = 3800  # 假设 position_y 的最大值为 4000
    min_x = 600
    min_y = 300
    middle_point_x = 2150
    middle_point_y = 2150
    normalized_x = normalize(position_x, min_x, max_value_x, middle_point_x)
    normalized_y = normalize(position_y, min_y, max_value_y, middle_point_y)

    # 反转 X 轴，因为设备的 X 轴方向与屏幕相反
    inverted_y = 1 - normalized_y

    # print(normalized_y, normalized_y)

    # 根据比例计算实际屏幕坐标
    top_left = positions["PP_4"]  # 左上角
    top_right = positions["PP_3"]  # 右上角
    bottom_left = positions["PP_1"]  # 左下角
    bottom_right = positions["PP_2"]  # 右下角

    screen_x = top_left[0] + normalized_x * (top_right[0] - top_left[0])
    screen_y = top_left[1] + inverted_y * (bottom_left[1] - top_left[1])
    # print(f"Screen coordinates: ({screen_x}, {screen_y})")

    return [screen_x, screen_y]


@app.route('/query_pp', methods=['GET'])  # todo: 待测试后删除
def query_pp():
    global recent_data_from_serial, base_position_x, base_position_y, abnormal_positions
    try:
        x = 1  # 或从请求中获取x的值
        if x < 1:
            return jsonify(error="Invalid value for x. x must be a positive integer."), 400

        # 调用计算平均值的函数，并更新全局pp_averages字典
        global pp_averages
        new_averages = calculate_average_pp(recent_data_from_serial, x)
        pp_averages.update(new_averages)  # 更新全局字典

        if abnormal_positions:
            if recent_data_from_serial:
                for entry in recent_data_from_serial:
                    if 'Position_X' in entry and 'Position_Y' in entry:
                        base_position_x = int(entry.split('Position_X:')[1].split(';')[0])
                        base_position_y = int(entry.split('Position_Y:')[1].split(';')[0])

            abnormal_positions = [base_position_x, base_position_y]  # 重置异常坐标记录

        return jsonify(pp_averages=pp_averages), 200

    except ValueError:
        return jsonify(error="Invalid value for x. x must be an integer."), 400


@app.route('/latest_paper_code', methods=['GET'])
def latest_paper_code():
    global current_paper
    if len(recent_data_from_serial) >= 2:
        # 提取最近两次数据的paper_code
        try:
            code_1 = int(recent_data_from_serial[-1].split('paper_code=')[-1].split(';')[0])

            # 检查是否相同并返回对应图片链接或0
            if code_1 in paper_code_to_image_url:
                current_paper = code_1
                return jsonify(image_url=paper_code_to_image_url[code_1])
            else:
                return jsonify(image_url=0)
        except (IndexError, ValueError) as e:
            # 如果解析出错，则返回错误信息
            return jsonify(error="Failed to parse paper_code or paper_code not found."), 400
    else:
        # 如果数据不足两次，则返回错误信息
        return jsonify(error="Not enough data for comparison."), 400


def parse_seal_data(entry=""):
    global recent_data_from_serial, seal_no
    if not recent_data_from_serial or len(recent_data_from_serial) < 1:
        print(recent_data_from_serial)
        return None
    if not entry and recent_data_from_serial:
        entry = recent_data_from_serial[0]
    else:
        return None

    try:
        if 'seal1_out=' in entry:
            if int(entry.split('seal1_out=')[-1].split(';')[0]) == 0:
                seal_out_status = 0
            else:
                seal_out_status = 1
        elif 'seal2_out=' in entry:
            if int(entry.split('seal2_out=')[-1].split(';')[0]) == 0:
                seal_out_status = 0
            else:
                seal_out_status = 2
        else:
            seal_out_status = 0

        seal_status = '拿起' if seal_out_status != 0 else '未拿起'
        seal_no = seal_out_status

        if seal_out_status != 0:

            # seal_azimuth_info = entry.split('seal_azimuth=')[-1]
            # seal_magx = float(seal_azimuth_info.split('Magx:')[1].split(',')[0])
            # seal_magy = float(seal_azimuth_info.split('Magy:')[1].split(',')[0])
            # seal_magz = float(seal_azimuth_info.split('Magz:')[1].split(',')[0])
            if seal_out_status == 1:
                seal_yaw = float(entry.split('seal1_Yaw=')[1].split(';')[0])
            else:
                seal_yaw = float(entry.split('seal2_Yaw=')[1].split(';')[0])
            angle = seal_yaw
            # angle = angle - (angle % 5)
            # print("调整前：" + str(seal_yaw) + "调整后：" + str(angle))
            # print(angle)

            return {
                'status': seal_status,
                "no": seal_out_status,
                'seal_azimuth': {
                    # 'Magx': seal_magx,
                    # 'Magy': seal_magy,
                    # 'Magz': seal_magz,
                    'Yaw': angle,
                    'seal_img': seal_dict[seal_out_status]["正"],
                }
            }
        else:
            return {'status': seal_status}
    except (IndexError, ValueError):
        # 返回None表示解析失败
        return None


@app.route('/seal_status', methods=['GET'])
def seal_status():
    # 尝试解析最新的数据，如果失败，则尝试解析前一条数据
    result = parse_seal_data()
    if result:
        return jsonify(result)

    # 如果两次尝试都失败了，返回错误提示
    return jsonify(status='数据解析失败', error="无法从最近的数据中解析印章状态，请检查数据格式和完整性"), 400


@app.route('/seal_data')
def seal_data():
    global is_pressing, scores
    try:
        result, [x, y], r, _scores = calculate_diff_pp()
    except:
        result = None

    if result is None:
        # 如果没有有效地按压结果，返回一个状态消息
        return jsonify({"seal": False, "is_pressing": is_pressing_pos})

    else:
        # 否则返回计算得到的位置和图像
        data = {
            "seal": True,
            "top": y,
            "left": x,
            "rotation": r,
            "image_url": result,
            "is_pressing": is_pressing_pos,
            "scores": _scores
        }
        scores = {
            'seal_no': False,
            'angle': 5,
            'press': 5,
            'no_slip': 25,
            'location': 5
        }
        print(data)

        return jsonify(data)


@app.route('/check_reset', methods=['GET'])
def check_reset():
    global recent_data_from_serial
    found_reset = False

    with data_lock:  # 使用锁确保线程安全
        # 遍历记录，检查是否包含 'Reset'
        for i, data in enumerate(recent_data_from_serial):
            if 'Reset' in data:
                found_reset = True
                # 替换掉 'Reset' 字符串
                recent_data_from_serial[i] = data.replace('Reset', '')

        # 如果发现 'Reset'，可选择性地执行额外的操作，如清空列表
        if found_reset:
            # 清空列表的操作，根据需求可注释或修改
            # recent_data_from_serial.clear()

            # 写入更新后的数据到文件
            write_data_to_file(recent_data_from_serial)

    return jsonify({'found_reset': found_reset})


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5050/")


if __name__ == '__main__':
    serial_thread = Thread(target=read_serial_data)
    serial_thread.daemon = True  # 设置为守护线程，这样当主程序退出时线程也会退出
    serial_thread.start()
    # Timer(1, open_browser).start()
    app.run(debug=True, threaded=True, port=5050)

# pyinstaller -F --add-data="static;static" --add-data="templates;templates" --add-data="config.json:." main.py
