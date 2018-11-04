from setuptools import setup
setup(
    name='garbageman',
    packages=['garbageman'],
    install_requires=['matplotlib', 'pandas', 'geopandas', 'rtree', 'tqdm'],
    py_modules=['pipeline', 'utils'],
    version='0.0.1',
    description='Data processing and visualization utilities for working with trash data',
    author='Aleksey Bilogur',
    author_email='aleksey.bilogur@gmail.com',
    url='https://github.com/ResidentMario/trash-talk',
    keywords=['data', 'data visualization', 'data analysis'],
    classifiers=[]
)
