"""Minimal Airflow-style DAG: DAG and task definitions."""
from datetime import datetime

def make_dag():
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    dag = DAG("example", start_date=datetime(2024, 1, 1), schedule=None)
    task_a = PythonOperator(task_id="extract", python_callable=lambda: 1, dag=dag)
    task_b = PythonOperator(task_id="transform", python_callable=lambda: 2, dag=dag)
    task_a >> task_b
    return dag
