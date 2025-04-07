import torch
import os
from data_preprocessing import PreprocessAndCache_for_single
import numpy as np
import zipfile
from model_with_gate import BFPCNet1
import pandas as pd
from doubao import get_book
import albumentations as A
from transformers import AutoTokenizer, AutoModel
from timm.data.constants import IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD
import mysql.connector
from sql_APIs import *
import re
mean = IMAGENET_DEFAULT_MEAN
std = IMAGENET_DEFAULT_STD
one_hot = {
    "N":0,
    "D":1,
    "G":2,
    "C":3,
    "A":4,
    "H":5,
    "M":6,
    "O":7,
}

one_hot_to_name = {
    "0":"正常",
    "1":"糖尿病",
    "2":"青光眼",
    "3":"白内障",
    "4":"AMD",
    "5":"高血压",
    "6":"近视",
    "7":"其他疾病/异常 ",
}

def parse_medical_record(text):
    """解析医疗记录文本并转换为字典格式（不保留换行）"""
    result = {}
    lines = text.splitlines()  # 处理不同平台的换行符
    current_key = None
    current_value = []

    for line in lines:
        line = line.strip()  # 清除前后空格
        if not line:
            continue  # 跳过空行

        match = re.match(r"([^:：]+)[：:](.*)", line)  # 兼容全角/半角冒号
        if match:
            if current_key is not None:
                result[current_key] = " ".join(current_value).strip()
            
            current_key = match.group(1).strip()
            current_value = [match.group(2).strip()]
        else:
            if current_key is not None:
                current_value.append(line.strip())  # 追加时用空格连接

    if current_key is not None:
        result[current_key] = " ".join(current_value).strip()

    return result

def get_augmentations2():
    return A.Compose([
        A.Normalize(mean, std),
],additional_targets={'right':'image'})
class Predict:
    def __init__(self,model_path,device,visualize=False):
        #模型还没搞好，这部分可以先不用看
        self.model = BFPCNet1(num_classes=8)
        map_location = torch.device('cpu') if device == "cpu" else None
        self.model.load_state_dict(torch.load(model_path, map_location=map_location), strict=False)
        self.model.to(device)
        self.model.eval()
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained("./biobert_model/")
        self.bertmodel = AutoModel.from_pretrained("./biobert_model/") 
        self.transform = get_augmentations2()
        self.visualize = visualize
        self.user_id = 1

    def extract_images_from_zip(self, zip_path, extract_dir):
        """从压缩包中提取图像文件"""
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        return extract_dir

    def predict(self, 
                left_img=None,
                right_img=None,
                texts=None,
                patient_id=None,
                patrint_name="张三",
                patiend_gender=None,
                patiend_age=None, 
                imgs=None, 
                xlxs=None, 
                mode="single"):
        answers = []
        
        if texts is None:  # 处理无文本情况
            if mode == "single":
                # 仅保留文件名
                left_img_name = os.path.splitext(os.path.basename(left_img))[0]
                right_img_name = os.path.splitext(os.path.basename(right_img))[0]

                process = PreprocessAndCache_for_single(left_img, right_img, cache_dir="./temp_cache")
                cache_path = f"./temp_cache/{left_img_name}_{right_img_name}.npz"

                single_data = np.load(cache_path)
                data = single_data["img"]
                l = data[:, :224, :]
                r = data[:, 224:, :]
                au = self.transform(image=l, right=r)
                data = np.concatenate((au['image'], au['right']), axis=1)
                
                data = torch.tensor(data).to(self.device).permute(2, 0, 1).float()
                data = data.unsqueeze(0)
                
                with torch.no_grad():
                    labels = self.model(data)
                labels = labels.squeeze(0)
                labels = (labels > 0.5).float()

                for i in range(8):
                    if labels[i] == 1:
                        answers.append(one_hot_to_name[str(i)])

                return answers
            
            elif mode == "batch":
                if xlxs is None:
                    raise ValueError("信息表路径不能为空")
                
                # 如果imgs是压缩包，先提取图像
                if imgs.endswith('.zip'):
                    extract_dir = "./temp_images"
                    imgs = self.extract_images_from_zip(imgs, extract_dir)
                
                # 读取信息表
                df = pd.read_excel(xlxs)
                batch_results = {}

                for _, row in df.iterrows():
                    patient_id = row.get('ID', '')
                    left_img_path = os.path.join(imgs, row['Left-Fundus'])
                    right_img_path = os.path.join(imgs, row['Right-Fundus'])

                    if os.path.exists(left_img_path) and os.path.exists(right_img_path):
                        left_img_name = os.path.splitext(os.path.basename(left_img_path))[0]
                        right_img_name = os.path.splitext(os.path.basename(right_img_path))[0]

                        process = PreprocessAndCache_for_single(left_img_path, right_img_path, cache_dir="./temp_cache")
                        cache_path = f"./temp_cache/{left_img_name}_{right_img_name}.npz"

                        single_data = np.load(cache_path)
                        data = single_data["img"]
                        l = data[:, :224, :]
                        r = data[:, 224:, :]
                        au = self.transform(image=l, right=r)
                        data = np.concatenate((au['image'], au['right']), axis=1)
                        
                        data = torch.tensor(data).to(self.device).permute(2, 0, 1).float()
                        data = data.unsqueeze(0)

                        with torch.no_grad():
                            labels = self.model(data)
                        labels = labels.squeeze(0)
                        labels = (labels > 0.5).float()

                        result_key = patient_id if (patient_id != None)else f"{left_img_name}_{right_img_name}"
                        
                        batch_results[result_key] = []
                        for i in range(8):
                            if labels[i] == 1:
                                batch_results[result_key].append(one_hot_to_name[str(i)])

                return batch_results
        
        else:  # 处理带文本情况
            if mode == "single":
                left_img_name = os.path.splitext(os.path.basename(left_img))[0]
                right_img_name = os.path.splitext(os.path.basename(right_img))[0]
                #print(left_img)
                save_left_img = read_image_file(left_img)
                save_right_img = read_image_file(right_img)
                #print(save_left_img)
                process = PreprocessAndCache_for_single(left_img, right_img, cache_dir="./temp_cache",text=texts)
                cache_path = f"./temp_cache/{left_img_name}_{right_img_name}.npz"

                single_data = np.load(cache_path)
                data = single_data["img"]
                l = data[:, :224, :]
                r = data[:, 224:, :]
                au = self.transform(image = l,right=r)
                data = np.concatenate((au['image'],au['right']), axis=1)

 
                texts_ori = str(single_data["left_keywords"]) + "," + str(single_data["right_keywords"])

                inputs = self.tokenizer(texts_ori, return_tensors="pt")
                with torch.no_grad():
                    outputs = self.bertmodel(**inputs)
                    last_hidden_state = outputs.last_hidden_state  # shape: (batch_size, seq_len, hidden_dim)
                    cls_embedding = last_hidden_state[:, 0, :]  # shape: (batch_size, hidden_dim)
                    text_embedding = cls_embedding

                data = torch.tensor(data).to(self.device).permute(2, 0, 1).float()
                data = data.unsqueeze(0)
                labels = self.model(data, text_embedding)
                labels = labels.squeeze(0)
                labels = (labels > 0.5).float()

                for i in range(8):
                    if labels[i] == 1:
                        answers.append(one_hot_to_name[str(i)])

                ans_str = ""

                for i in answers:
                    ans_str += i +','

                advise = get_book(
                    patient_name=patrint_name,
                    patient_age=patiend_age,
                    patient_sex=patiend_gender,
                    patient_disease=ans_str,

                )

                save_results(
                    patient_id=patient_id,
                    patient_name=patrint_name,
                    patient_age=patiend_age,
                    patient_sex=patiend_gender,
                    predict_result=ans_str,
                    advise=advise,
                    fund_id = None,
                    left_fund_keyword=texts["left_text"],
                    right_fund_keyword=texts["right_text"],
                    left_fund=save_left_img,
                    right_fund=save_right_img,
           
                )
                advise = parse_medical_record(advise)
                return ans_str,advise
            
            elif mode == "batch":
                if xlxs is None:
                    raise ValueError("信息表路径不能为空")
                
                # 如果imgs是压缩包，先提取图像
                if imgs.endswith('.zip'):
                    extract_dir = "./temp_images"
                    imgs = self.extract_images_from_zip(imgs, extract_dir)
                
                # 读取信息表
                df = pd.read_excel(xlxs)
                batch_results = {}

                for _, row in df.iterrows():
                    patient_id = row.get('ID', '')
                    left_img_path = os.path.join(imgs, row['Left-Fundus'])
                    right_img_path = os.path.join(imgs, row['Right-Fundus'])
                    
                    # 获取诊断关键词
                    left_keywords = str(row['Left-Diagnostic Keywords'])
                    right_keywords = str(row['Right-Diagnostic Keywords'])
                    
                    text = {
                        "left_text": left_keywords,
                        "right_text": right_keywords
                    }

                    if os.path.exists(left_img_path) and os.path.exists(right_img_path):
                        left_img_name = os.path.splitext(os.path.basename(left_img_path))[0]
                        right_img_name = os.path.splitext(os.path.basename(right_img_path))[0]

                        process = PreprocessAndCache_for_single(left_img_path, right_img_path, cache_dir="./temp_cache", text=text)
                        cache_path = f"./temp_cache/{left_img_name}_{right_img_name}.npz"

                        single_data = np.load(cache_path)
                        data = single_data["img"]
                        l = data[:, :224, :]
                        r = data[:, 224:, :]
                        au = self.transform(image=l, right=r)
                        data = np.concatenate((au['image'], au['right']), axis=1)
                        
                        texts = str(single_data["left_keywords"]) + "," + str(single_data["right_keywords"])
                        
                        inputs = self.tokenizer(texts, return_tensors="pt")
                        with torch.no_grad():
                            outputs = self.bertmodel(**inputs)
                            last_hidden_state = outputs.last_hidden_state
                            cls_embedding = last_hidden_state[:, 0, :]
                            text_embedding = cls_embedding
                        
                        data = torch.tensor(data).to(self.device).permute(2, 0, 1).float()
                        data = data.unsqueeze(0)
                        
                        labels = self.model(data, text_embedding)
                        labels = labels.squeeze(0)
                        labels = (labels > 0.5).float()
                        
                        result_key = patient_id if (patient_id != None) else f"{left_img_name}_{right_img_name}"
                        
                        # 收集预测结果
                        prediction_results = []
                        for i in range(8):
                            if labels[i] == 1:
                                prediction_results.append(one_hot_to_name[str(i)])
                        
                        # 构建预测结果字符串
                        ans_str = ",".join(prediction_results)
                        
                        # 获取患者信息
                        patient_name = "张三"
                        patient_age = row.get('Patient Age', None)
                        patient_gender = row.get('Patient Sex', None)
                        
                        # 生成建议
                        advise = get_book(
                            patient_name=patient_name,
                            patient_age=patient_age,
                            patient_sex=patient_gender,
                            patient_disease=ans_str,
                        )
                        
                        # 保存结果到数据库
                        save_left_img = read_image_file(left_img_path)
                        save_right_img = read_image_file(right_img_path)
                        
                        record_id, fund_id = save_results(
                            patient_id=patient_id,
                            patient_name=patient_name,
                            patient_age=patient_age,
                            patient_sex=patient_gender,
                            predict_result=ans_str,
                            advise=advise,
                            fund_id=None,
                            left_fund_keyword=left_keywords,
                            right_fund_keyword=right_keywords,
                            left_fund=save_left_img,
                            right_fund=save_right_img,
                        )
                        
                        batch_results[result_key] = {
                            'predictions': prediction_results,
                            'record_id': record_id,
                            'fund_id': fund_id
                        }
                
                return batch_results


if __name__ == "__main__":
    # annotation_path = r"F:\BFPC/real_full/Off-site Test Set\Annotation/off-site test annotation (English).xlsx"
    # image_folder = r"F:\BFPC/real_full/Off-site Test Set/Images"  # 存储图像的文件夹
    # output_csv = r"F:\BFPC/real_full/Off-site Test Set/predictions.csv"  # 输出的 CSV 文件路径

    # # 加载预测模型
    # p = Predict("F:\BFPC/final_model_state_dict_with_gate.pth", device="cpu")

    # # 读取 Excel 文件
    # df = pd.read_excel(annotation_path)

    # # 结果存储列表
    # results = []

    # # 遍历所有行进行预测
    # for _, row in df.iterrows():
    #     left_img_path = os.path.join(image_folder, row["Left-Fundus"])
    #     right_img_path = os.path.join(image_folder, row["Right-Fundus"])

    #     # 确保图像文件存在
    #     if not os.path.exists(left_img_path) or not os.path.exists(right_img_path):
    #         print(f"警告：未找到图像 {left_img_path} 或 {right_img_path}，跳过...")
    #         continue

    #     # 构造文本输入
    #     text = {
    #         "left_text": str(row["Left-Diagnostic Keywords"]),
    #         "right_text": str(row["Right-Diagnostic Keywords"])
    #     }

    #     # 进行预测
    #     predictions = p.predict(left_img_path, right_img_path, texts=text)

    #     # 存储结果
    #     results.append([row["ID"]] + [1 if one_hot_to_name[str(i)] in predictions else 0 for i in range(8)])

    # # 创建 DataFrame 并保存为 CSV
    # columns = ["ID"] + list(one_hot_to_name.values())  # 列名
    # df_results = pd.DataFrame(results, columns=columns)
    # df_results.to_csv(output_csv, index=False, encoding="utf-8")

    # print(f"预测完成，结果已保存至 {output_csv}")
    
    # p = Predict("F:\BFPC/final_model_state_dict_with_gate.pth", device="cpu")
    # res = p.predict(imgs="F:\BFPC\ceshi\ceshi.zip",xlxs="F:\BFPC\ceshi\ceshi.xlsx",texts=True,mode="batch")
    # print(res)
    # import os

    # path = "./biobert_model/"
    # print("Path exists:", os.path.exists(path))
    # print("Contents:", os.listdir(path) if os.path.exists(path) else "Directory not found")

    p = Predict("F:\BFPC/final_model_state_dict_with_gate.pth", device="cpu")
    res = p.predict(left_img="F:\BFPC\cropped_#Training_Dataset/0_left.jpg",right_img="F:\BFPC\cropped_#Training_Dataset/0_right.jpg",
                    texts={
                        'left_text':"wrwr",
                        "right_text":"fwfefwe",
                    },
                    patiend_age=23,
                    patiend_gender="Male",
                    patrint_name="张三",
                    mode="single",
                    patient_id=1,
                    )

    print(res)

