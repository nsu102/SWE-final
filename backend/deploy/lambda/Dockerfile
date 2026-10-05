FROM public.ecr.aws/lambda/python:3.12
ENV HF_HOME=/opt/huggingface TRANSFORMERS_CACHE=/opt/huggingface PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
COPY requirements-backend.txt requirements-ml.txt requirements-aws.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-backend.txt -r ${LAMBDA_TASK_ROOT}/requirements-ml.txt -r ${LAMBDA_TASK_ROOT}/requirements-aws.txt
COPY deploy/lambda/cache_models.py /tmp/cache_models.py
RUN python /tmp/cache_models.py && chmod -R a+rX /opt/huggingface
COPY src ${LAMBDA_TASK_ROOT}/src
# Catalog seed (34,777 products, ~12MB) for SeedFunction: the private RDS is only reachable from the VPC.
COPY seed ${LAMBDA_TASK_ROOT}/seed
CMD ["src.backend.lambda_handler.handler"]
