import asyncio
async def work(name, sec):
    print(f"{name} started")
    await asyncio.sleep(sec)
    print(f"{name} finished")

async def main():
    await asyncio.gather(
        work("task1", 2),
        work("task2", 4),
        work("task3", 1),
        work("task4", 5),
    )

if __name__ == "__main__":
    import time
    start_time = time.time()
    asyncio.run(main())
    total_time = time.time() - start_time
    print(f"All tasks completed in {total_time:.2f} seconds")