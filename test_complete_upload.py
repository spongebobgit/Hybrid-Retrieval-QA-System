#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整文件上传功能测试脚本
包括：上传、日志查询、回滚、删除等功能

注意：运行前需要启动FastAPI服务（python app.py）
"""

import requests
import os
import json
import time
from pathlib import Path

# FastAPI服务器地址
BASE_URL = "http://localhost:8001"

def print_response(label, response):
    """打印响应信息"""
    print(f"\n{label}:")
    print(f"  状态码: {response.status_code}")
    try:
        data = response.json()
        print(f"  响应内容: {json.dumps(data, ensure_ascii=False, indent=2)}")
    except:
        print(f"  响应内容: {response.text}")

def test_health():
    """测试健康检查端点"""
    response = requests.get(f"{BASE_URL}/health")
    print_response("健康检查", response)
    return response.status_code == 200

def test_get_sources():
    """测试获取学科类别"""
    response = requests.get(f"{BASE_URL}/api/sources")
    print_response("获取学科类别", response)
    return response.status_code == 200

def test_get_stats():
    """测试获取知识库统计"""
    response = requests.get(f"{BASE_URL}/api/knowledgebase/stats")
    print_response("知识库统计", response)
    return response.status_code == 200

def create_test_file(filename, content=None):
    """创建测试文件"""
    if content is None:
        content = f"这是一个测试文档内容，用于测试文件上传功能。\n创建时间: {time.time()}\n"

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"创建测试文件: {filename}")
    return filename

def test_upload_file(file_path, source="test"):
    """测试上传文件并返回日志ID"""
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return None

    files = {'files': open(file_path, 'rb')}
    data = {'source': source} if source else {}

    try:
        response = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
        print_response(f"上传文件 {file_path}", response)

        if response.status_code == 200:
            data = response.json()
            return data.get('log_id')
        return None
    except Exception as e:
        print(f"上传失败: {e}")
        return None
    finally:
        if 'files' in locals():
            files['files'].close()

def test_get_upload_logs(source=None, limit=10):
    """测试获取上传日志"""
    params = {'limit': limit}
    if source:
        params['source'] = source

    response = requests.get(f"{BASE_URL}/api/upload/logs", params=params)
    print_response(f"获取上传日志 (source={source}, limit={limit})", response)

    if response.status_code == 200:
        data = response.json()
        return data.get('logs', [])
    return []

def test_delete_upload_log(log_id):
    """测试删除上传日志"""
    response = requests.delete(f"{BASE_URL}/api/upload/logs/{log_id}")
    print_response(f"删除上传日志 {log_id}", response)
    return response.status_code == 200

def test_rollback_upload(log_id):
    """测试回滚上传"""
    response = requests.post(f"{BASE_URL}/api/upload/rollback/{log_id}")
    print_response(f"回滚上传 {log_id}", response)
    return response.status_code == 200

def test_delete_knowledgebase(source):
    """测试删除知识库文档"""
    response = requests.delete(f"{BASE_URL}/api/knowledgebase/{source}")
    print_response(f"删除知识库文档 {source}", response)
    return response.status_code == 200

def main():
    """主测试函数"""
    print("=== 完整文件上传功能测试 ===\n")

    # 检查服务器是否运行
    if not test_health():
        print("服务器未运行，请先启动: python app.py")
        return

    # 获取学科类别
    if not test_get_sources():
        print("获取学科类别失败")
        return

    # 获取当前统计
    test_get_stats()

    # 获取当前上传日志
    logs_before = test_get_upload_logs()

    # 创建测试文件
    test_filename1 = "test_document_1.txt"
    test_filename2 = "test_document_2.txt"

    create_test_file(test_filename1, "这是第一个测试文档，用于测试上传功能。")
    create_test_file(test_filename2, "这是第二个测试文档，用于测试多个文件上传。")

    print("\n=== 测试阶段1: 单个文件上传 ===")
    log_id1 = test_upload_file(test_filename1, source="test")

    # 等待处理完成
    time.sleep(2)

    # 获取上传后的统计
    print("\n上传后统计:")
    test_get_stats()

    # 获取上传日志
    logs_after1 = test_get_upload_logs()
    print(f"上传前日志数: {len(logs_before)}, 上传后日志数: {len(logs_after1)}")

    print("\n=== 测试阶段2: 多个文件上传 ===")
    # 测试多个文件上传（使用同一个文件两次模拟多个文件）
    log_id2 = test_upload_file(test_filename2, source="test")

    # 等待处理完成
    time.sleep(2)

    # 获取特定学科的日志
    test_get_upload_logs(source="test")

    print("\n=== 测试阶段3: 回滚操作 ===")
    if log_id1:
        print(f"回滚第一个上传 (log_id={log_id1})")
        test_rollback_upload(log_id1)

        # 等待回滚完成
        time.sleep(1)

        # 回滚后统计
        print("\n回滚后统计:")
        test_get_stats()
    else:
        print("没有可回滚的日志ID")

    print("\n=== 测试阶段4: 日志管理 ===")
    # 获取所有日志
    all_logs = test_get_upload_logs()

    # 测试删除日志（如果有多个日志）
    if len(all_logs) > 1:
        last_log = all_logs[-1]
        test_delete_upload_log(last_log['id'])

    print("\n=== 测试阶段5: 知识库管理 ===")
    # 测试删除学科文档（警告：这将删除所有test学科的文档）
    # test_delete_knowledgebase("test")

    # 清理测试文件
    for filename in [test_filename1, test_filename2]:
        if os.path.exists(filename):
            os.remove(filename)
            print(f"清理测试文件: {filename}")

    print("\n=== 最终统计 ===")
    test_get_stats()

    final_logs = test_get_upload_logs()
    print(f"最终日志总数: {len(final_logs)}")

    print("\n=== 测试完成 ===")
    print("提示：要查看详细结果，请检查上面的响应内容。")

if __name__ == "__main__":
    main()