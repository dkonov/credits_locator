import unittest
from structure_credits import reconstruct,structure
class StructureTest(unittest.TestCase):
    def test_same_person_two_roles(self):
        def frame(t,ys):
            return {'time_sec':t,'lines':[{'text':text,'bbox':[x,y,x+.12,y+.02],'confidence':95}
              for text,x,y in [('Монтаж',.3,ys[0]),('Иван Иванов',.54,ys[0]),('Продюсер',.3,ys[1]),('Иван Иванов',.54,ys[1])]]}
        data=[frame(0,[.3,.6]),frame(1,[.2,.5]),frame(2,[.1,.4])]
        tracks,speed=reconstruct(data)
        credits,review=structure(tracks)
        self.assertAlmostEqual(speed,-.1)
        self.assertEqual(len(credits),2)
        self.assertEqual({x['role'] for x in credits},{'Монтаж','Продюсер'})
        self.assertEqual(review,[])
if __name__=='__main__':unittest.main()
