import argparse
import sys
import cv2
import numpy as np
from picamera2 import MappedArray, Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics, postprocess_nanodet_detection

# 初始化变量
last_detections = []
total_detected_persons = 0  # 用于统计检测到的总人数
active_detections = []  # 用于存储当前场景中的活跃检测框
iou_threshold = 0.5  # IoU 阈值，用于判断是否是同一个人

class Detection:
    def __init__(self, coords, category, conf, metadata):
        """Create a Detection object, recording the bounding box, category and confidence."""
        self.category = category
        self.conf = conf
        self.box = coords  # 存储边界框坐标

def iou(box1, box2):
    """计算两个边界框的IoU（交并比）"""
    # box1 和 box2 都是边界框坐标 (x1, y1, x2, y2)
    x1, y1, x2, y2 = box1
    x1_p, y1_p, x2_p, y2_p = box2

    # 计算交集区域
    inter_x1 = max(x1, x1_p)
    inter_y1 = max(y1, y1_p)
    inter_x2 = min(x2, x2_p)
    inter_y2 = min(y2, y2_p)

    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)

    # 计算并集区域
    area1 = (x2 - x1) * (y2 - y1)
    area2 = (x2_p - x1_p) * (y2_p - y1_p)

    union_area = area1 + area2 - inter_area

    return inter_area / union_area

def parse_detections(metadata: dict):
    """Parse the output tensor into a number of detected objects, scaled to the ISP output."""
    global last_detections, total_detected_persons, active_detections
    threshold = 0.55  # Detection threshold
    max_detections = 10  # Max detections per frame

    np_outputs = imx500.get_outputs(metadata, add_batch=True)
    input_w, input_h = imx500.get_input_size()
    if np_outputs is None:
        return last_detections

    # Process detections
    boxes, scores, classes = np_outputs[0][0], np_outputs[1][0], np_outputs[2][0]
    boxes = np.array_split(boxes, 4, axis=1)
    boxes = zip(*boxes)

    last_detections = [
        Detection(box, category, score, metadata)
        for box, score, category in zip(boxes, scores, classes)
        if score > threshold
    ]

    # 过滤掉重复检测
    new_detections = []
    for detection in last_detections:
        is_new_detection = True
        for active_detection in active_detections:
            # 从Detection对象中提取框坐标并计算IoU
            if iou(detection.box, active_detection.box) > iou_threshold:
                is_new_detection = False
                break
        if is_new_detection:
            new_detections.append(detection)
            active_detections.append(detection)  # 新检测到的人，加入到活跃检测中

    # 更新总人数
    total_detected_persons += len(new_detections)

    # 清除已经离开画面的人
    active_detections = [d for d in active_detections if any(iou(d.box, nd.box) > iou_threshold for nd in new_detections)]

    return new_detections

def draw_detections(request, stream="main"):
    """Draw the detections for this request onto the ISP output."""
    detections = last_detections
    if detections is None:
        return
    with MappedArray(request, stream) as m:
        for detection in detections:
            # 确保 detection.box 是合法的 (x, y, w, h) 格式
            x, y, w, h = detection.box  # 获取检测框的坐标和宽高

            # 为矩形的右下角计算坐标
            x2 = x + w
            y2 = y + h

            label = f"Person ({detection.conf:.2f})"

            # 计算文本大小和位置
            (text_width, text_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            text_x = x + 5
            text_y = y + 15

            # 创建一个副本的背景，带有透明度
            overlay = m.array.copy()

            # 在覆盖物上绘制背景矩形
            cv2.rectangle(overlay,
                          (text_x, text_y - text_height),
                          (text_x + text_width, text_y + baseline),
                          (255, 255, 255),  # 背景颜色（白色）
                          cv2.FILLED)

            alpha = 0.30
            cv2.addWeighted(overlay, alpha, m.array, 1 - alpha, 0, m.array)

            # 在背景上绘制文本
            cv2.putText(m.array, label, (text_x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

            # 绘制检测框
            cv2.rectangle(m.array, (x, y), (x2, y2), (0, 255, 0), thickness=2)  # 这里使用 x2, y2

        # 在左上角显示总人数
        cv2.putText(m.array, f"Total Persons: {total_detected_persons}", (10, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

def get_labels():
    # 这里添加获取标签的逻辑
    return ["label1", "label2", "label3"]

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, help="Path of the model",
                        default="/usr/share/imx500-models/imx500_network_ssd_mobilenetv2_fpnlite_320x320_pp.rpk")
    parser.add_argument("--fps", type=int, help="Frames per second")
    parser.add_argument("--bbox-normalization", action=argparse.BooleanOptionalAction, help="Normalize bbox")
    parser.add_argument("--bbox-order", choices=["yx", "xy"], default="yx",
                        help="Set bbox order yx -> (y0, x0, y1, x1) xy -> (x0, y0, x1, y1)")
    parser.add_argument("--threshold", type=float, default=0.55, help="Detection threshold")
    parser.add_argument("--iou", type=float, default=0.65, help="Set iou threshold")
    parser.add_argument("--max-detections", type=int, default=10, help="Set max detections")
    parser.add_argument("--ignore-dash-labels", action=argparse.BooleanOptionalAction, help="Remove '-' labels ")
    parser.add_argument("--postprocess", choices=["", "nanodet"],
                        default=None, help="Run post process of type")
    parser.add_argument("-r", "--preserve-aspect-ratio", action=argparse.BooleanOptionalAction,
                        help="preserve the pixel aspect ratio of the input tensor")
    parser.add_argument("--labels", type=str,
                        help="Path to the labels file")
    parser.add_argument("--print-intrinsics", action="store_true",
                        help="Print JSON network_intrinsics then exit")
    return parser.parse_args()


if __name__ == "__main__":
    args = get_args()

    # This must be called before instantiation of Picamera2
    imx500 = IMX500(args.model)
    intrinsics = imx500.network_intrinsics
    if not intrinsics:
        intrinsics = NetworkIntrinsics()
        intrinsics.task = "object detection"
    elif intrinsics.task != "object detection":
        print("Network is not an object detection task", file=sys.stderr)
        exit()

    # Override intrinsics from args
    for key, value in vars(args).items():
        if key == 'labels' and value is not None:
            with open(value, 'r') as f:
                intrinsics.labels = f.read().splitlines()
        elif hasattr(intrinsics, key) and value is not None:
            setattr(intrinsics, key, value)

    # Defaults
    if intrinsics.labels is None:
        with open("assets/coco_labels.txt", "r") as f:
            intrinsics.labels = f.read().splitlines()
    intrinsics.update_with_defaults()

    picam2 = Picamera2(imx500.camera_num)
    config = picam2.create_preview_configuration(controls={"FrameRate": intrinsics.inference_rate}, buffer_count=12)

    imx500.show_network_fw_progress_bar()
    picam2.start(config, show_preview=True)

    if intrinsics.preserve_aspect_ratio:
        imx500.set_auto_aspect_ratio()

    last_results = None
    picam2.pre_callback = draw_detections
    while True:
        last_results = parse_detections(picam2.capture_metadata())
