import json
import os
import time
from threading import Thread, Lock

import serial
from flask import Flask, render_template, jsonify

data_lock = Lock()

app = Flask(__name__)

# 全局变量用于存储从单片机读取的数据
data_from_serial = "等待数据中..."
recent_data_from_serial = []
file_path = "data.json"

avg_magx, avg_magy, avg_magz = 0, 0, 0
# 初始化用于存储PP平均值的全局字典
pp_averages = {"PP_1": 0, "PP_2": 0, "PP_3": 0, "PP_4": 0, "PP_5": 0}
# 全局变量用于跟踪按压状态和最大按压值
is_pressing = False
max_press_value = 0
max_press_key = None
max_press_location = None
max_press_rotation = 0

seal_move_x = 0
seal_move_y = 0
seal_move_diff = 400
seal_is_moved = False

sleep_count = 0
time_count = 0

# paper_code与图片链接的映射字典
paper_code_to_image_url = {
    111222333: "static/盖章实训文件（中秋）_01.png",
    123454321: "static/22.jpg",
    111222444: "static/建设工程施工合同_01.png",
    111222555: "static/联合发文_01.png",
    111222666: "static/11.png"

    # 添加更多的映射
}

current_paper = 0
seal_location_dict = {
    111222666: [64.6, 50],
    # 111222333: [0, 0],
    111222333: [54, 65],
}

correct_seal = 3

# 印章图片路径
seal_no = 0,
seal_dict = {
    0: {"正": "static/公章-正.png", "浅": "static/公章-浅.png", "深": "static/公章-深.png", "移": "static/公章-移.png"},
    # 默认章
    1: {"正": "static/公章-服装-正.png", "浅": "static/公章-服装-浅.png", "深": "static/公章-服装-深.png",
        "移": "static/公章-服装-移.png"},
    2: {"正": "static/公章-建筑-正.png", "浅": "static/公章-建筑-浅.png", "深": "static/公章-建筑-深.png",
        "移": "static/公章-建筑-移.png"},
    3: {"正": "static/公章-建筑-正.png", "浅": "static/公章-建筑-浅.png", "深": "static/公章-建筑-深.png",
            "移": "static/公章-建筑-移.png"},

}


def write_data_to_file(data):
    """将数据写入文件"""
    with open(file_path, 'w') as f:
        json.dump(data, f)


def read_data_from_file():
    """从文件读取数据"""
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return []


# 尝试打开串行端口并在后台读取数据的函数
def read_serial_data():
    ser = None
    buffer = ""  # 用于累积从串行端口读取的数据

    try:
        ser = serial.Serial('COM3', 9600, timeout=1)  # 设置超时为None以持续等待数据

        while True:
            data = ser.read(ser.in_waiting or 1).decode('iso-8859-1')  # 读取所有可用的数据
            buffer += data  # 将新数据追加到缓冲区

            start_pos = buffer.find('$')
            if start_pos != -1:
                end_pos = buffer.find('$', start_pos + 1)
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


def calculate_average(c_data):
    magx_sum = []
    magy_sum = []
    magz_sum = []
    count = min(len(c_data), 2)  # 取最近的3次数据或者全部数据（如果不足3次）

    for i in range(count):
        entry = c_data[i].split(',')
        for item in entry:
            if 'Magx' in item:
                magx_sum.append(int(item.split(':')[-1]))
            elif 'Magy' in item:
                magy_sum.append(int(item.split(':')[-1]))
            elif 'Magz' in item:
                magz_sum.append(int(item.split(':')[-1]))

    # 计算平均值
    avg_magx = sum(magx_sum) / len(magx_sum) if len(magx_sum) != 0 else 0
    avg_magy = sum(magy_sum) / len(magy_sum) if len(magy_sum) != 0 else 0
    avg_magz = sum(magz_sum) / len(magz_sum) if len(magz_sum) != 0 else 0

    return avg_magx, avg_magy, avg_magz


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/test')
def test():
    return render_template('test.html')


@app.route('/data')
def data():
    global recent_data_from_serial
    _data = read_data_from_file()

    recent_data_from_serial = _data

    if recent_data_from_serial:
        return jsonify(data=''.join(str(item) for item in recent_data_from_serial))
    else:
        return jsonify(data=data_from_serial)


# 计算最近3次数据中的平均值
@app.route('/calculate_average', methods=['GET'])
def calculate_average_endpoint():
    global avg_magx, avg_magy, avg_magz
    try:
        avg_magx, avg_magy, avg_magz = calculate_average(recent_data_from_serial)
        return jsonify({'avg_magx': avg_magx, 'avg_magy': avg_magy, 'avg_magz': avg_magz})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 查询最近的平均值
@app.route('/query_average', methods=['GET'])
def query_average_endpoint():
    global avg_magx, avg_magy, avg_magz
    return jsonify({'avg_magx': avg_magx, 'avg_magy': avg_magy, 'avg_magz': avg_magz})


def calculate_average_pp(data, x):
    # 初始化临时存储平均值的字典
    temp_averages = {}
    # 假设data是最近的数据列表，x是考虑的数据数量
    for pp_key in ["PP_1", "PP_2", "PP_3", "PP_4", "PP_5"]:
        pp_values = [int(entry.split(pp_key + '=')[1].split(';')[0]) for entry in data[-x:] if pp_key + '=' in entry]
        if pp_values:
            temp_averages[pp_key] = sum(pp_values) / len(pp_values)
    return temp_averages


def sleep_count_tick(sleep_count):
    if sleep_count > 0:
        return sleep_count - 1
    return 0


def calculate_diff_pp():
    global pp_averages, is_pressing, max_press_value, max_press_key, max_press_location, max_press_rotation, seal_move_x, seal_move_y, seal_move_diff, seal_is_moved, sleep_count, time_count
    scores = {
        'seal_no': False,
        'angle': 5,
        'press': 5,
        'no_slip': 25,
        'location': 5
    }

    sleep_count = sleep_count_tick(sleep_count)
    time_count = sleep_count_tick(time_count)

    if pp_averages == {"PP_1": 0, "PP_2": 0, "PP_3": 0, "PP_4": 0, "PP_5": 0}:
        return None, [50, 50], 0, scores

    new_dict = calculate_average_pp(recent_data_from_serial, 1)
    diff_dict = {key: int(new_dict[key]) - int(pp_averages[key]) for key in ["PP_1", "PP_2", "PP_3", "PP_4"]}

    current_max_diff = max(diff_dict.values())
    current_max_key = max(diff_dict, key=diff_dict.get)  # 获取当前最大压力位置

    # 每次计算新的位置
    current_location = calculate_press_location(diff_dict)
    r = parse_seal_data()

        # print(current_rotation, scores['angle'])
            # current_rotation = current_rotation + 0.1 / 1.5



    # 更新最大按压值、位置和对应的位置
    if current_max_diff > max_press_value:
        max_press_value = current_max_diff
        max_press_key = current_max_key  # 更新最大压力位置
        max_press_location = current_location  # 更新位置记录


        if r["status"] == '拿起' and seal_move_x != 0 and seal_move_y != 0:
            if abs(seal_move_x - r["seal_azimuth"]["Magx"]) > seal_move_diff:
                seal_is_moved = True
            if abs(seal_move_y - r["seal_azimuth"]["Magy"]) > seal_move_diff:
                seal_is_moved = True
        print(seal_is_moved)

    if is_pressing:
        print(
            f"Pressing... Current Max Value: {max_press_value}, Location: {max_press_location}, Rotation:{max_press_rotation}")

    # 检测按压开始和结束
    if current_max_diff > 10000 and not is_pressing and sleep_count == 0 and (r and r["status"] == '拿起'):
        print("【开始按压】")
        is_pressing = True
        seal_move_x = r["seal_azimuth"]["Magx"]
        seal_move_y = r["seal_azimuth"]["Magy"]
        seal_is_moved = False
        time_count = 20
        if r and r["status"] == '拿起':
            current_rotation = r["seal_azimuth"]["Yaw"] if r else 0

            if -15 <= current_rotation <= 15:
                scores['angle'] = 25
            elif -30 <= current_rotation <= 30:
                scores['angle'] = 15
            elif -45 <= current_rotation <= 45:
                scores['angle'] = 10
            else:
                scores['angle'] = 0

        max_press_rotation = current_rotation
        print(seal_is_moved)


    # elif (current_max_diff < 10000 or current_max_diff < (max_press_value + 1) / 2 or time_count == 0) and is_pressing:
    elif (current_max_diff < 10000 or current_max_diff < (
            max_press_value + 1) / 2 or time_count == 0) and is_pressing:
        # 按压结束，返回最大按压值时的位置和结果
        is_pressing = False
        sleep_count = 30
        if max_press_value in range(200000, 500000):
            scores['press'] = 25
        elif max_press_value in range(10000, 200000):
            scores['press'] = 15

        if seal_is_moved:
            scores['no_slip'] = 5
        if seal_no == correct_seal:
            scores['seal_no'] = True

        location_range = 5

        if current_paper != 0 and current_paper in seal_location_dict.keys():
            if current_paper == 111222666:
                if abs(max_press_location[0] - seal_location_dict[current_paper][0]) < 1 and abs(
                        max_press_location[1] - seal_location_dict[current_paper][1]) < 1:
                    scores['location'] = 25
                    max_press_location[0] = seal_location_dict[current_paper][0]
                    max_press_location[1] = seal_location_dict[current_paper][1]
                else:
                    scores['location'] = 0
            else:
                if abs(max_press_location[0] - seal_location_dict[current_paper][0]) < location_range and abs(
                        max_press_location[1] - seal_location_dict[current_paper][1]) < location_range:
                    scores['location'] = 25
                    max_press_location[0] = seal_location_dict[current_paper][0]
                    max_press_location[1] = seal_location_dict[current_paper][1]
                elif abs(max_press_location[0] - seal_location_dict[current_paper][0]) < location_range * 2 and abs(
                        max_press_location[1] - seal_location_dict[current_paper][1]) < location_range * 2:
                    scores['location'] = 15

        result = get_press_result(max_press_value, seal_is_moved)
        print(
            f"【按压结束】 Max Value: {max_press_value}, Result: {result}, Location: {max_press_location}, Rotation:{max_press_rotation}")
        print(scores)
        print(seal_is_moved)
        seal_is_moved = False
        max_press_value = 0  # 重置最大按压值
        max_press_key = None  # 重置最大压力位置
        last_location = max_press_location  # 保存最后的位置
        last_rotation = max_press_rotation
        max_press_location = None  # 重置位置记录
        max_press_rotation = 0
        print(last_location)
        return result, last_location, last_rotation, scores

    return None, [50, 50], 0, scores


def get_press_result(press_value, seal_is_moved):
    global seal_no, seal_dict
    if press_value < 200000:
        return seal_dict[seal_no]["浅"]
    elif press_value < 500000:
        if seal_is_moved:
            return seal_dict[seal_no]["移"]
        else:
            return seal_dict[seal_no]["正"]
    else:
        return seal_dict[seal_no]["深"]


def calculate_press_location(diff_dict):
    # 每个角的位置坐标
    positions = {
        "PP_1": (100, 35),  # 左下角
        "PP_2": (100, 65),  # 右下角
        "PP_3": (0, 65),  # 右上角
        "PP_4": (0, 35)  # 左上角
    }
    if current_paper == 111222666:
        positions = {
            "PP_1": (55, 30),  # 左下角
            "PP_2": (55, 70),  # 右下角
            "PP_3": (45, 70),  # 右上角
            "PP_4": (45, 30)  # 左上角
        }

    total_weight = sum(diff_dict.values())
    if total_weight == 0:
        return 50, 50  # 默认位置（防止除以零错误）

    # 计算加权平均的位置
    weighted_sum_x = sum(positions[key][1] * weight for key, weight in diff_dict.items())
    weighted_sum_y = sum(positions[key][0] * weight for key, weight in diff_dict.items())

    # 计算最终的x和y坐标
    x = weighted_sum_x / total_weight
    y = weighted_sum_y / total_weight

    return [x, y]


@app.route('/diff_pp', methods=['GET'])
def get_diff_pp():
    out = calculate_diff_pp()
    return jsonify(pp_location=out), 200


@app.route('/query_pp', methods=['GET'])
def query_pp():
    try:
        x = 1  # 或从请求中获取x的值
        if x < 1:
            return jsonify(error="Invalid value for x. x must be a positive integer."), 400

        # 调用计算平均值的函数，并更新全局pp_averages字典
        global pp_averages
        new_averages = calculate_average_pp(recent_data_from_serial, x)
        pp_averages.update(new_averages)  # 更新全局字典

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
            # code_2 = int(recent_data_from_serial[-2].split('paper_code=')[-1].split(';')[0])

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
    if not entry and recent_data_from_serial:
        entry = recent_data_from_serial[1]
    else:
        return None
    try:
        seal_out_status = int(entry.split('seal_out=')[-1].split(';')[0])
        seal_status = '拿起' if seal_out_status != 0 else '未拿起'
        seal_no = seal_out_status

        if seal_out_status != 0:

            seal_azimuth_info = entry.split('seal_azimuth=')[-1]
            seal_magx = float(seal_azimuth_info.split('Magx:')[1].split(',')[0])
            seal_magy = float(seal_azimuth_info.split('Magy:')[1].split(',')[0])
            seal_magz = float(seal_azimuth_info.split('Magz:')[1].split(',')[0])
            seal_yaw = -float(seal_azimuth_info.split('Yaw:')[1].split(';')[0])
            angle = seal_yaw
            # angle = angle - (angle % 5)
            # print("调整前：" + str(seal_yaw) + "调整后：" + str(angle))

            return {
                'status': seal_status,
                "no": seal_out_status,
                'seal_azimuth': {
                    'Magx': seal_magx,
                    'Magy': seal_magy,
                    'Magz': seal_magz,
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
    global is_pressing
    result, [x, y], r, scores = calculate_diff_pp()

    if result is None:
        # 如果没有有效地按压结果，返回一个状态消息
        return jsonify({"seal": False, "is_pressing": is_pressing})

    else:
        # 否则返回计算得到的位置和图像
        data = {
            "seal": True,
            "top": y,
            "left": x,
            "rotation": r,
            "image_url": result,
            "is_pressing": is_pressing,
            "scores": scores
        }
        print(data)
        return jsonify(data)


if __name__ == '__main__':
    serial_thread = Thread(target=read_serial_data)
    serial_thread.daemon = True  # 设置为守护线程，这样当主程序退出时线程也会退出
    serial_thread.start()

    app.run(debug=True, threaded=True)
