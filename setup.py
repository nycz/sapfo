from setuptools import setup, find_packages

setup(
    name='sapfo',
    version='1.5.0',
    description='Organize your novel/story writing files',
    url='https://github.com/nycz/sapfo',
    author='nycz',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: X11 Applications :: Qt',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Topic :: Other/Nonlisted Topic',
    ],
    packages=find_packages(exclude=['thoughts', 'tests']),
    install_requires=['PyQt5', 'libsyntyche'],
    include_package_data=True,
    entry_points={
        'gui_scripts': [
            'sapfo=sapfo.sapfo:main'
        ]
    }
)
