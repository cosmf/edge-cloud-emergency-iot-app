from confluent_kafka import Consumer, Producer, KafkaError
import threading
import json
import time
import uuid
import signal
import random
import string

stop_event = threading.Event()


def handle_sigint(signal_num, frame):
    print("\nSIGINT received. Stopping thread...")
    stop_event.set()


def random_char(char_num):
    return "".join(random.choice(string.ascii_letters) for _ in range(char_num))


def generate_email_address():
    return f"{random_char(7)}@gmail.com"


class KafkaConsumer(threading.Thread):
    def __init__(self, topics, id, group_id, stop_event: threading.Event):
        """Initialize thread with topics and thread id."""
        threading.Thread.__init__(self)
        self.__topics = topics
        self.__id = id
        self.__group_id = group_id
        self.__stop_event = stop_event

    def run(self):
        """Launch a thread that runs indefinitely to handle events."""
        conf = {
            "bootstrap.servers": "localhost:19092",
            "group.id": self.__group_id,
        }

        consumer = Consumer(conf)
        consumer.subscribe(topics=self.__topics)
        try:
            while not self.__stop_event.is_set():
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() != KafkaError._PARTITION_EOF:
                        print(f"Error: {msg.error()}")
                else:
                    print(
                        f"Consumer {self.__id}: {msg.value().decode('utf-8')} (key: {msg.key()})\n"
                    )
                    consumer.commit(msg)
        finally:
            consumer.close()


"""
    TODO3: Copy-paste the `producer.produce` line 5 times.
    TODO3: Add a `key` parameter with a different string value.
    TODO3: Run the script. What is the result?
"""
class KafkaProducer(threading.Thread):

    def __init__(self, topic: str, stop_event: threading.Event):
        """Initialize thread with topic and data."""
        threading.Thread.__init__(self)
        self.__topic = topic
        self.__stop_event = stop_event

    def run(self):
        """Launch a thread that runs indefinitely to produce events."""
        conf = {"bootstrap.servers": "localhost:19092"}

        producer = Producer(conf)

        while not self.__stop_event.is_set():
            data = {
                "to": "Sergiu Weisz",
                "from": generate_email_address(),
                "message": "Much teacher, such joy",
            }
            # producer.produce(topic=self.__topic, value=json.dumps(data))

            producer.produce(topic=self.__topic, value=json.dumps({"event": "login", "user": "user_1"}), key="user_1")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "add_to_cart", "user": "user_2"}), key="user_2")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "logout", "user": "user_1"}), key="user_1")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "view_item", "user": "user_3"}), key="user_3")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "search", "user": "user_4"}), key="user_4")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "checkout", "user": "user_2"}), key="user_2")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "share", "user": "user_5"}), key="user_5")
            producer.produce(topic=self.__topic, value=json.dumps({"event": "like", "user": "user_6"}), key="user_6") # More Keys
            producer.produce(topic=self.__topic, value=json.dumps({"event": "comment", "user": "user_7"}), key="user_7") # More Keys

            
            producer.flush()
            time.sleep(1)


"""
    TODO1: Increase the number of consumer threads to 2 and execute the script. What is the result?
    TODO2: Use the same group id for both consumer threads and run the script.
    TODO3: start 3 consumers.
"""
def main():

    consumerThreads = list()
    consumersNumber = 3
    group_id = "invoice-services"


    #  Signal that catches CTRL+C and stops threads
    signal.signal(signal.SIGINT, handle_sigint)

    for i in range(0, consumersNumber):
        # group_id = uuid.uuid4()
        consumerThread = KafkaConsumer(
            topics=["post.office"], id=i, group_id=group_id, stop_event=stop_event
        )
        consumerThreads.append(consumerThread)
    producerThread = KafkaProducer(topic="post.office", stop_event=stop_event)

    for thread in consumerThreads:
        thread.start()
    time.sleep(1)
    producerThread.start()

    for thread in consumerThreads:
        thread.join()
    producerThread.join()


if __name__ == "__main__":
    main()
