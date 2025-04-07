from flask import Flask, request, jsonify, send_from_directory, abort, send_file
from flask_cors import CORS
import shutil
from predict import Predict
import os
import mimetypes
from data_preprocessing import PreprocessAndCache_for_single
import matplotlib.pyplot as plt
import base64
from io import BytesIO
from cut_blend import cut_blend
from sql_APIs import get_patient_records , get_recent_records , get_fund_info
from diagnostic_report_generator import create_diagnostic_pdf,make_styles_data
from plot_apis import main

app = Flask(__name__, static_folder='./frontend/dist')
CORS(app)  # Enable CORS on all routes

# 初始化 Predict 类
model_path = "./final_model_state_dict_with_gate.pth"
predictor = Predict(model_path, device="cpu")

@app.route('/predict', methods=['POST'])
def predict():
    left_eye_file = request.files['left_eye']
    right_eye_file = request.files['right_eye']
    left_eye_text = request.form.get('left_eye_text')
    right_eye_text = request.form.get('right_eye_text')
    patient_id = request.form.get('patientId')
    patient_name = request.form.get('patientName')
    patient_gender = request.form.get('patientGender')
    patient_age = request.form.get('patientAge')
    if not os.path.exists("temp"):
        os.makedirs("temp")
    
    left_eye_file_path = os.path.join("temp", left_eye_file.filename)
    right_eye_file_path = os.path.join("temp", right_eye_file.filename)

    left_eye_file_path = left_eye_file_path.replace("\\", "/")
    right_eye_file_path = right_eye_file_path.replace("\\", "/")

    left_eye_file.save(left_eye_file_path)
    right_eye_file.save(right_eye_file_path)

    pre=PreprocessAndCache_for_single(left_img="./"+left_eye_file_path, right_img="./"+right_eye_file_path,pre=True)
    img_left = pre.preprocess_img("./" + left_eye_file_path)
    img_right = pre.preprocess_img("./" + right_eye_file_path)
    img_left_x1,img_left_x2 = cut_blend("./"+left_eye_file_path)
    img_right_y1,img_right_y2 = cut_blend("./"+right_eye_file_path)
    # 将图像保存为 JPG 文件并转换为Base64编码
    img_left_x1_buffer = BytesIO()
    plt.imsave(img_left_x1_buffer, img_left_x1, format='jpg')
    img_left_x1_base64 = base64.b64encode(img_left_x1_buffer.getvalue()).decode('utf-8')

    img_left_x2_buffer = BytesIO()
    plt.imsave(img_left_x2_buffer, img_left_x2, format='jpg')
    img_left_x2_base64 = base64.b64encode(img_left_x2_buffer.getvalue()).decode('utf-8')

    img_right_y1_buffer = BytesIO()
    plt.imsave(img_right_y1_buffer, img_right_y1, format='jpg')
    img_right_y1_base64 = base64.b64encode(img_right_y1_buffer.getvalue()).decode('utf-8')


    img_right_y2_buffer = BytesIO()
    plt.imsave(img_right_y2_buffer, img_right_y2, format='jpg')
    img_right_y2_base64 = base64.b64encode(img_right_y2_buffer.getvalue()).decode('utf-8')
    result = predictor.predict(left_img="./"+left_eye_file_path, right_img="./"+right_eye_file_path,texts={
        "left_text": left_eye_text,
        "right_text": right_eye_text,
    },patient_id=patient_id,
    patrint_name=patient_name,
    patiend_gender=patient_gender,
    patiend_age=patient_age, mode="single")

    merged = pre.merge_double_imgs("./" + left_eye_file_path, "./" + right_eye_file_path)
    merged_buffer = BytesIO()
    plt.imsave(merged_buffer, merged, format='jpg')
    merged_base64 = base64.b64encode(merged_buffer.getvalue()).decode('utf-8')
    os.remove(left_eye_file_path)
    os.remove(right_eye_file_path)

    print(result)
    return jsonify({
        'merged_base64': merged_base64,
        'left_eye_x1': img_left_x1_base64,
        'left_eye_x2': img_left_x2_base64,
        'right_eye_y1': img_right_y1_base64,
        'right_eye_y2': img_right_y2_base64,
        'result': result
    }), 200

    # try:
    #     if 'zip_file' in request.files:
    #         zip_file = request.files['zip_file']

    #         if not os.path.exists("temp"):
    #             os.makedirs("temp")

    #         zip_path = os.path.join("temp", zip_file.filename)

    #         zip_path = zip_path.replace("\\", "/")

    #         zip_file.save(zip_path)

    #         results = predictor.predict(imgs=zip_path, mode="batch")

    #         os.remove(zip_path)

    #         return jsonify(results)

    #     elif 'left_eye' in request.files and 'right_eye' in request.files:
    #         left_eye_file = request.files['left_eye']
    #         right_eye_file = request.files['right_eye']

    #         if not os.path.exists("temp"):
    #             os.makedirs("temp")

    #         left_eye_path = os.path.join("temp", left_eye_file.filename)
    #         right_eye_path = os.path.join("temp", right_eye_file.filename)

    #         left_eye_path = left_eye_path.replace("\\", "/")
    #         right_eye_path = right_eye_path.replace("\\", "/")

    #         left_eye_file.save(left_eye_path)
    #         right_eye_file.save(right_eye_path)

    #         results = predictor.predict(left_img=left_eye_path, right_img=right_eye_path, mode="single")

    #         os.remove(left_eye_path)
    #         os.remove(right_eye_path)

    #         return jsonify(results)

    #     else:
    #         return jsonify({'error': 'Both left_eye and right_eye files are required or a zip_file is required'}), 400
    # except Exception as e:
    #     if os.path.exists("temp"):
    #         shutil.rmtree("temp")
    #     return jsonify({'error': str(e)}), 500

@app.route('/get_patient_record', methods=['POST'])
def get_patient_record():
    print("get_patient_record",request.get_json())
    patient_id = request.get_json()['id']
    print("patient_id",patient_id)
    record = get_patient_records(patient_id)
    return jsonify(record), 200
@app.route('/get_recent_record', methods=['POST'])
def get_recent_record():
    print("get_recent_record",request.get_json())
    limit = request.get_json()['limit']
    record = get_recent_records(limit)
    return jsonify(record), 200
@app.route('/get_fund_infoX', methods=['POST'])
def get_fund_infoX():
    print("get_fund_info",request.get_json())
    fund_id = request.get_json()['fund_id']
    print("fund_id",fund_id)
    record = get_fund_info(fund_id)
    result=make_styles_data(record)
    return jsonify(result), 200
@app.route('/create_pdf', methods=['POST'])
def create_pdf():
    print("create_pdf",request.get_json())
    pdf_data = request.get_json()
    pdf_file=create_diagnostic_pdf(pdf_data['data'])
    return send_file(
            pdf_file,
            as_attachment=True,
            download_name="diagnostic_report.pdf",
            mimetype='application/pdf'
        )
@app.route('/batch_analysis', methods=['POST'])
def batch_analysis():
    print("Content-Type:", request.content_type)  # 打印请求的 Content-Type
    print("create_pdf", request.files)

    # 获取上传的文件
    images_zip = request.files.get('images_zip')  # 获取名为 'images_zip' 的文件
    patient_data = request.files.get('patient_data')  # 获取名为 'patient_data' 的文件

    # 打印文件信息
    print("images_zip:", images_zip.filename if images_zip else "No file uploaded")
    print("patient_data:", patient_data.filename if patient_data else "No file uploaded")

    if not images_zip or not patient_data:
        return jsonify({"error": "Missing required files"}), 400

    # 保存文件到临时目录
    if not os.path.exists("temp"):
        os.makedirs("temp")

    images_zip_path = os.path.join("temp", images_zip.filename)
    patient_data_path = os.path.join("temp", patient_data.filename)

    images_zip.save(images_zip_path)
    patient_data.save(patient_data_path)

    print(f"Saved images_zip to {images_zip_path}")
    print(f"Saved patient_data to {patient_data_path}")

    # 调用 predictor.predict 方法，传递文件路径
    results = predictor.predict(imgs=images_zip_path, xlxs=patient_data_path, mode="batch",                    texts={
                        'left_text':"wrwr",
                        "right_text":"fwfefwe",
                    },)
    # 删除临时文件
    os.remove(images_zip_path)
    os.remove(patient_data_path)
    return jsonify(results), 200

file_path = './Traning_Dataset.xlsx'

@app.route('/get_plot', methods=['POST'])
def get_plot():
        # 获取原始统计数据
    stats = main(file_path, statistics=True)
    print("\n原始诊断统计数据:")
    print(f"总诊断数: {stats['total_diagnoses']}")
    print(f"正常样本: {stats['normal_samples']}")
    print(f"异常样本: {stats['abnormal_samples']}")
    print(f"准确率: {stats['accuracy']:.2f}%")
    
    return jsonify(stats), 200
@app.route('/get_plot_gender', methods=['POST'])
def get_plot_gender():
    # 获取分布数据
    flag_data = request.get_json()
    flag = flag_data.get('flag') 
    print("flag",flag)
    age_pct, gender_pct = main(file_path,flag=flag)
    
    # 打印调试信息
    print("\n年龄分布百分比:")
    print(age_pct)
    print("\n性别分布百分比:")
    print(gender_pct)
    
    # 将 Pandas Series 转换为字典
    age_pct_dict = age_pct.to_dict()
    gender_pct_dict = gender_pct.to_dict()
    
    result = {"age_pct": age_pct_dict, "gender_pct": gender_pct_dict}
    return jsonify(result), 200


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_static_file(path)
    else:
        return send_static_file('index.html')

def send_static_file(f: str):
    if os.path.isfile(app.static_folder + '/' + f):
        if f.endswith('.js'):
            mime_type = 'text/javascript'
        else:
            mimetypes.init()
            mime_type, _ = mimetypes.guess_type(f)
        print(f, mime_type)
        return send_from_directory(app.static_folder, f, mimetype=mime_type)
    else:
        abort(404)

if __name__ == '__main__':
    app.run(debug=False, port=5000)