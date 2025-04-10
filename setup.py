from setuptools import setup

setup(
    name='CloudWatcher',
    version='1.0.0',    
    description='CloudWatcher API to MQTT Publisher',
    url='https://github.com/AstronomyAcres/CloudWatcher',
    author='Michael J. Kidd',
    license='GPL-3.0',
    scripts=['CloudWatcher/cw2mqtt.py'],
    packages=['CloudWatcher'],
    install_requires=[],

    classifiers=[
        'Development Status :: 1 - Initial release',
        'Intended Audience :: Astronomers/Coders',
        'License :: OSI Approved :: GNU General Public License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3.9',
    ],
)
