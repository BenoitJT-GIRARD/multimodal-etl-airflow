"""Measurements on the collected dataset, kept apart from the pipeline that produces it.

These modules read a dataset and return numbers. They never write to the database and never
reach the network, which is what makes them testable on a hand-built DataFrame.
"""
