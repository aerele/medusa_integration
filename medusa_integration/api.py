import frappe
import requests
import json


def create_medusa_product():
	url = "http://localhost:9000/admin/products/"

	payload = json.dumps({
		"title": "Hey1",
		"handle": "",
		"discountable": True,
		"is_giftcard": False,
		"description": "333",
		"options": [],
		"variants": [],
		"status": "published",
		"sales_channels": []
	})
	headers = {
		'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidXNyXzAxSFlGUEtGU0FHRTk0RDE0ODM4RFIyRlFRIiwiZG9tYWluIjoiYWRtaW4iLCJpYXQiOjE3MTYzNzExMDAsImV4cCI6MTcxNjQ1NzUwMH0.D2xx3AVspw34yJxfWcGZTOCPf5N-ScmQo-hS2uedwlM',
		'Content-Type': 'application/json',
		'Cookie': 'connect.sid=s%3AMFilIbqUknKzhiXUZ8YLvWjmq7OZTYbc.9xHOpFVY2NN%2F8fv0dVbi3%2BB1JT7rdyK6nQgrBS2F0D4'
	}

	response = requests.request("POST", url, headers=headers, data=payload)

	print(response.text)
