__author__ = "Rohan B. Dalton"


class Engine(object):
    def __init__(self, cylinders: int, volume: float):
        self.cylinders = cylinders
        self.volume = volume


class Drivetrain(object):
    def __init__(self, wheels: int, drive: int):
        self.drive = drive
        self.wheels = wheels


class Car(object):
    def __init__(self, engine: Engine, drivetrain: Drivetrain):
        self.engine = engine
        self.drivetrain = drivetrain


if __name__ == "__main__":
    pass
