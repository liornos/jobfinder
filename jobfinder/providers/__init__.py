from .greenhouse import GreenhouseProvider
from .lever import LeverProvider
from .ashby import AshbyProvider
from .smartrecruiters import SmartRecruitersProvider
PROVIDERS={'greenhouse':GreenhouseProvider(),'lever':LeverProvider(),'ashby':AshbyProvider(),'smartrecruiters':SmartRecruitersProvider()}
__all__=['PROVIDERS']
