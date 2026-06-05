from rq import Queue, Worker

from app.db.redis import get_rq_redis_client


def main() -> None:
    redis_client = get_rq_redis_client()
    redis_client.ping()
    queues = [Queue("default", connection=redis_client)]
    worker = Worker(queues, connection=redis_client, name="livelines-worker")
    worker.work()


if __name__ == "__main__":
    main()
